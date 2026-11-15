"""Ingestion pipeline (Stage 3D): pages -> chunks -> token check -> vectors -> store.

Two steps so the API can embed OUTSIDE its store lock and write INSIDE it:

1. `prepare_document(pages)`: chunk, count tokens, embed. Nothing is stored.
   A chunk longer than the model limit is never embedded (no silent
   truncation): `ChunksOverTokenLimit` is raised and the whole file fails,
   because quietly dropping text would make the index incomplete (decision D-033).
2. `store_document(prepared)`: delete the file's old chunks, upsert the new
   ones; if the write fails half-way, that file's chunks are removed again.

`rebuild_index()` re-reads every PDF in the uploads folder and rebuilds the
index from scratch (PDFs are the source of truth; Chroma is derived).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from backend.config import settings
from backend.ingestion.chunker import Chunk, chunk_pages
from backend.ingestion.pdf_loader import PageText, PdfLoadError, extract_pages
from backend.retrieval import services
from backend.retrieval.embedder import Embedder
from backend.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)


class ChunksOverTokenLimit(Exception):
    """Some chunks exceed the embedding model's token limit; nothing was embedded."""

    def __init__(self, over_limit: list[tuple[str, int]], max_tokens: int, max_chunk_tokens: int) -> None:
        self.over_limit = over_limit  # (chunk_id, token_count)
        self.max_tokens = max_tokens
        self.max_chunk_tokens = max_chunk_tokens
        super().__init__(
            f"{len(over_limit)} chunk(s) exceed the {max_tokens}-token embedding limit "
            f"(longest {max_chunk_tokens}); lower CHUNK_SIZE. Nothing was stored."
        )


@dataclass(frozen=True)
class PreparedDocument:
    file_name: str
    chunks: list[Chunk]
    vectors: list[list[float]]
    max_chunk_tokens: int

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


@dataclass
class RebuildReport:
    indexed: dict[str, int] = field(default_factory=dict)  # file -> chunk count
    failed: dict[str, str] = field(default_factory=dict)  # file -> reason


def prepare_document(
    file_name: str,
    pages: list[PageText],
    embedder: Embedder | None = None,
    *,
    token_aware: bool | None = None,
) -> PreparedDocument:
    embedder = embedder or services.get_embedder()
    max_tokens = embedder.max_tokens
    use_token_aware = settings.token_aware_chunking if token_aware is None else token_aware
    if use_token_aware and max_tokens > 0:
        chunks = chunk_pages(
            pages,
            settings.chunk_size,
            settings.chunk_overlap,
            max_tokens=max_tokens,
            token_counter=embedder.count_tokens,
        )
    else:
        chunks = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)

    counts = [embedder.count_tokens(c.text) for c in chunks]
    over = [(c.chunk_id, n) for c, n in zip(chunks, counts) if n > max_tokens]
    if over:
        raise ChunksOverTokenLimit(over, max_tokens, max(counts))

    vectors: list[list[float]] = []
    batch = settings.embedding_batch_size
    for start in range(0, len(chunks), batch):
        embedded = embedder.embed_documents([c.text for c in chunks[start : start + batch]])
        vectors.extend(e.vector for e in embedded)
    return PreparedDocument(file_name, chunks, vectors, max(counts, default=0))


def store_document(prepared: PreparedDocument, store: VectorStore | None = None) -> None:
    """Replace the file's chunks. On failure, leave none of its chunks behind."""
    if not prepared.chunks:
        return
    store = store or services.get_store()
    try:
        store.delete_file(prepared.file_name)
        store.upsert_chunks(
            ids=[c.chunk_id for c in prepared.chunks],
            documents=[c.text for c in prepared.chunks],
            embeddings=prepared.vectors,
            file_names=[c.file_name for c in prepared.chunks],
            page_numbers=[c.page_number for c in prepared.chunks],
            chunk_indices=[c.chunk_index for c in prepared.chunks],
        )
    except Exception:
        _remove_quietly(store, prepared.file_name)
        raise


def _remove_quietly(store: VectorStore, file_name: str) -> None:
    try:
        store.delete_file(file_name)
    except Exception:
        logger.exception("Could not remove partial chunks of %s; run rebuild_index()", file_name)


def ingest_pages(
    file_name: str,
    pages: list[PageText],
    *,
    token_aware: bool | None = None,
) -> PreparedDocument:
    prepared = prepare_document(file_name, pages, token_aware=token_aware)
    store_document(prepared)
    return prepared


def rebuild_index(
    uploads_dir: Path | None = None,
    sample_dir: Path | None = None,
    *,
    token_aware: bool | None = None,
) -> RebuildReport:
    """Throw the index away and rebuild it from both sample PDFs and user uploads."""
    uploads_dir = Path(uploads_dir or settings.uploads_dir)
    sample_dir_to_use = Path(sample_dir or getattr(settings, "sample_dir", uploads_dir.parent / "sample_pdfs"))
    store = services.get_store()
    store.clear()
    report = RebuildReport()

    pdf_paths: list[Path] = []
    if sample_dir_to_use.is_dir():
        pdf_paths.extend(p for p in sample_dir_to_use.rglob("*.pdf") if p.is_file())
    if uploads_dir.is_dir():
        pdf_paths.extend(
            p for p in uploads_dir.iterdir()
            if p.is_file() and p.suffix.lower() == ".pdf" and not p.name.startswith(".upload-")
        )

    # De-duplicate by file name (user upload overrides sample if same name)
    unique_pdfs: dict[str, Path] = {p.name: p for p in pdf_paths}

    for name, path in sorted(unique_pdfs.items(), key=lambda kv: kv[0].lower()):
        try:
            prepared = prepare_document(path.name, extract_pages(path, path.name), token_aware=token_aware)
            store_document(prepared, store)
            report.indexed[path.name] = prepared.chunk_count
        except (PdfLoadError, ChunksOverTokenLimit) as error:
            report.failed[path.name] = str(error)
        except Exception as error:  # one bad file must not stop the rebuild
            logger.exception("Rebuild failed for %s", path.name)
            report.failed[path.name] = f"{type(error).__name__}: {error}"
    return report
