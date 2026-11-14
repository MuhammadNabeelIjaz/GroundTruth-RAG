"""ChromaDB vector store (Stage 3C).

One collection, cosine distance, `embedding_function=None` on EVERY open (so
Chroma never attaches its own default model). Findings from Stage 3A that
shape this file:

- `get_or_create_collection` silently ignores a different configuration, so
  `_ensure_open` reads the configuration back and compares it itself;
- `add()` silently ignores duplicate ids, so only `upsert()` is used;
- Chroma accepts a zero or wrong-shaped vector in some paths, so
  `verify_index` checks dimension and norm itself;
- an empty batch raises, so it is rejected explicitly.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)

_MAX_SAFE_BATCH = 256  # Chroma's hard limit is 5461
_SPACE = "cosine"
_NORM_TOLERANCE = 1e-3


class CollectionConfigError(RuntimeError):
    """The stored collection was made with a different model/dimension/space."""


class EmptyBatchError(ValueError):
    """upsert_chunks() was called with nothing to store."""


@dataclass(frozen=True)
class IndexIssue:
    kind: str  # bad_vector | bad_metadata | orphan_chunk | unindexed_file | self_retrieval_failed
    detail: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    file_name: str
    page_number: int
    chunk_index: int
    similarity: float  # 1 - cosine distance


def _client(chroma_dir: Path):
    return chromadb.PersistentClient(
        path=str(chroma_dir), settings=ChromaSettings(anonymized_telemetry=False)
    )


def open_collection_or_none(chroma_dir: Path, collection_name: str):
    """Open an existing collection without creating anything; None if absent."""
    chroma_dir = Path(chroma_dir)
    if not chroma_dir.exists():
        return None
    try:
        return _client(chroma_dir).get_collection(name=collection_name, embedding_function=None)
    except chromadb.errors.NotFoundError:
        return None


def read_file_chunk_counts(chroma_dir: Path, collection_name: str) -> dict[str, int]:
    """{file_name: chunk count} read straight from Chroma; {} if nothing was indexed.

    Needs no embedding model, so listing documents never triggers a model load.
    """
    collection = open_collection_or_none(chroma_dir, collection_name)
    counts: dict[str, int] = {}
    if collection is None:
        return counts
    offset = 0
    while True:
        page = collection.get(include=["metadatas"], limit=_MAX_SAFE_BATCH, offset=offset)
        if not page["ids"]:
            return counts
        for meta in page["metadatas"]:
            counts[meta["file_name"]] = counts.get(meta["file_name"], 0) + 1
        offset += len(page["ids"])


def delete_file_chunks(chroma_dir: Path, collection_name: str, file_name: str) -> int:
    """Delete every chunk of a file; returns how many existed. No model needed."""
    collection = open_collection_or_none(chroma_dir, collection_name)
    if collection is None:
        return 0
    existing = len(collection.get(where={"file_name": file_name}, include=[])["ids"])
    collection.delete(where={"file_name": file_name})
    return existing


class VectorStore:
    def __init__(self, chroma_dir: Path, collection_name: str, embedding_model: str, dimension: int) -> None:
        self._chroma_dir = Path(chroma_dir)
        self._collection_name = collection_name
        self._embedding_model = embedding_model
        self._dimension = dimension
        self._client = None
        self._collection = None
        self._lock = threading.RLock()

    # ---- opening -------------------------------------------------------

    def _ensure_open(self):
        with self._lock:
            if self._collection is not None:
                return self._collection
            self._chroma_dir.mkdir(parents=True, exist_ok=True)
            client = _client(self._chroma_dir)
            expected = {
                "embedding_model": self._embedding_model,
                "dimension": self._dimension,
                "space": _SPACE,
            }
            try:
                collection = client.get_collection(name=self._collection_name, embedding_function=None)
            except chromadb.errors.NotFoundError:
                collection = client.create_collection(
                    name=self._collection_name,
                    embedding_function=None,
                    configuration={"hnsw": {"space": _SPACE}},
                    metadata=expected,
                )
            self._verify_configuration(collection, expected)
            self._client = client
            self._collection = collection
            return collection

    def _verify_configuration(self, collection, expected: dict) -> None:
        stored = collection.metadata or {}
        for key, want in expected.items():
            if stored.get(key) != want:
                raise CollectionConfigError(
                    f"Collection {self._collection_name!r} was built with {key}="
                    f"{stored.get(key)!r} but the app is configured for {want!r}. "
                    "Rebuild the index (rebuild_index) or change the setting back."
                )
        space = self._read_space(collection)
        if space != _SPACE:
            raise CollectionConfigError(
                f"Collection {self._collection_name!r} uses distance {space!r}, expected {_SPACE!r}. "
                "Rebuild the index."
            )

    @staticmethod
    def _read_space(collection) -> str | None:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Chroma's legacy-config loader warns on read
            return (collection.configuration or {}).get("hnsw", {}).get("space")

    # ---- writes --------------------------------------------------------

    def upsert_chunks(
        self,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        file_names: list[str],
        page_numbers: list[int],
        chunk_indices: list[int],
    ) -> None:
        sizes = {len(ids), len(documents), len(embeddings), len(file_names), len(page_numbers), len(chunk_indices)}
        if len(sizes) != 1:
            raise ValueError("ids, documents, embeddings and metadata lists must have the same length.")
        if not ids:
            raise EmptyBatchError("Nothing to store: the batch is empty.")
        collection = self._ensure_open()
        for start in range(0, len(ids), _MAX_SAFE_BATCH):
            end = start + _MAX_SAFE_BATCH
            collection.upsert(
                ids=ids[start:end],
                documents=documents[start:end],
                embeddings=embeddings[start:end],
                metadatas=[
                    {"file_name": f, "page_number": int(p), "chunk_index": int(c)}
                    for f, p, c in zip(file_names[start:end], page_numbers[start:end], chunk_indices[start:end])
                ],
            )

    def delete_file(self, file_name: str) -> None:
        self._ensure_open().delete(where={"file_name": file_name})

    def clear(self) -> None:
        """Remove every chunk (used by rebuild_index)."""
        collection = self._ensure_open()
        ids = collection.get(include=[])["ids"]
        for start in range(0, len(ids), _MAX_SAFE_BATCH):
            collection.delete(ids=ids[start : start + _MAX_SAFE_BATCH])

    # ---- reads ---------------------------------------------------------

    def count(self) -> int:
        return self._ensure_open().count()

    def _iter_records(self, include: list[str]):
        collection = self._ensure_open()
        offset = 0
        while True:
            page = collection.get(include=include, limit=_MAX_SAFE_BATCH, offset=offset)
            if not page["ids"]:
                return
            yield page
            offset += len(page["ids"])

    def list_file_names(self) -> set[str]:
        names: set[str] = set()
        for page in self._iter_records(["metadatas"]):
            names.update(m["file_name"] for m in page["metadatas"])
        return names

    def file_chunk_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for page in self._iter_records(["metadatas"]):
            for m in page["metadatas"]:
                counts[m["file_name"]] = counts.get(m["file_name"], 0) + 1
        return counts

    def query(
        self,
        vector: list[float],
        top_k: int,
        file_names: list[str] | None = None,
    ) -> list[RetrievedChunk]:
        collection = self._ensure_open()
        n = min(top_k, collection.count())
        if n <= 0:
            return []
        kwargs: dict = {
            "query_embeddings": [vector],
            "n_results": n,
            "include": ["documents", "metadatas", "distances"],
        }
        if file_names:
            clean_names = [f for f in file_names if f]
            if len(clean_names) == 1:
                kwargs["where"] = {"file_name": {"$eq": clean_names[0]}}
            elif len(clean_names) > 1:
                kwargs["where"] = {"file_name": {"$in": clean_names}}
        raw = collection.query(**kwargs)
        return [
            RetrievedChunk(cid, doc, meta["file_name"], meta["page_number"], meta["chunk_index"], 1.0 - dist)
            for cid, doc, meta, dist in zip(
                raw["ids"][0], raw["documents"][0], raw["metadatas"][0], raw["distances"][0]
            )
        ]

    # ---- verification --------------------------------------------------

    def _check_vector(self, chunk_id: str, vector) -> IndexIssue | None:
        if len(vector) != self._dimension:
            return IndexIssue("bad_vector", f"{chunk_id}: {len(vector)} values, expected {self._dimension}")
        if not all(math.isfinite(float(x)) for x in vector):
            return IndexIssue("bad_vector", f"{chunk_id}: contains NaN or infinity")
        norm = math.sqrt(sum(float(x) * float(x) for x in vector))
        if abs(norm - 1.0) > _NORM_TOLERANCE:
            return IndexIssue("bad_vector", f"{chunk_id}: L2 norm {norm:.4f}, expected 1.0")
        return None

    def verify_index(self, disk_file_names: set[str]) -> list[IndexIssue]:
        issues: list[IndexIssue] = []
        indexed: set[str] = set()
        sample: tuple[str, str, list[float]] | None = None
        for page in self._iter_records(["embeddings", "metadatas", "documents"]):
            for cid, vec, meta, doc in zip(page["ids"], page["embeddings"], page["metadatas"], page["documents"]):
                indexed.add(meta["file_name"])
                bad = self._check_vector(cid, vec)
                if bad:
                    issues.append(bad)
                elif sample is None:
                    sample = (cid, doc, [float(x) for x in vec])
                expected_id = f"{meta['file_name']}:{meta['page_number']}:{meta['chunk_index']}"
                if cid != expected_id or meta["page_number"] < 1 or meta["chunk_index"] < 0:
                    issues.append(IndexIssue("bad_metadata", f"{cid}: metadata does not match the id"))
        for name in sorted(indexed - disk_file_names):
            issues.append(IndexIssue("orphan_chunk", f"{name} has chunks but no PDF on disk"))
        for name in sorted(disk_file_names - indexed):
            issues.append(IndexIssue("unindexed_file", f"{name} is on disk but has no chunks"))
        if sample is not None:
            cid, _doc, vec = sample
            top = self.query(vec, top_k=1)
            if not top or top[0].similarity < 1.0 - 1e-3:
                got = top[0].chunk_id if top else "nothing"
                issues.append(IndexIssue("self_retrieval_failed", f"{cid}: its own vector returned {got}"))
        return issues
