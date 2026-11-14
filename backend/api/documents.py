"""PDF upload endpoint.

Each uploaded file goes through the same steps, independently of the others:

1. sanitize the file name and check the `.pdf` extension (415)
2. refuse a name that already exists (409)
3. stream the upload into a temporary file, enforcing the size limit (413) and
   checking the `%PDF-` header (415) and that it is not empty (400)
4. extract the pages with the PDF loader (400 / 422 if the PDF is unusable)
5. only then, under a lock, check the name once more and move the temporary
   file to its final name

A file that fails at any step leaves nothing behind in the uploads folder.
The endpoint is a plain `def`, not `async def`: PyMuPDF blocks, and FastAPI runs
plain functions in a thread pool so other requests are not held up.
"""

import logging
import os
import tempfile
import threading
import unicodedata
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from backend.config import settings
from backend.ingestion import pdf_loader
from backend.ingestion.pdf_loader import PdfLoadError, extract_pages
from backend.ingestion import pipeline
from backend.retrieval import vector_store
from backend.schemas import (
    DeleteResponse,
    DocumentInfo,
    DocumentList,
    FileResult,
    OverLimitChunk,
    PagePreview,
    UploadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

PDF_MAGIC = b"%PDF-"
CHUNK_SIZE = 1024 * 1024  # copy uploads in 1 MiB pieces
MAX_NAME_LENGTH = 100  # characters, including ".pdf"
MAX_NAME_BYTES = 200  # UTF-8 bytes; file systems allow 255 bytes per name
PREVIEW_CHARS = 100
_TEMP_PREFIX = ".upload-"
_TEMP_SUFFIX = ".part"

# Held while the final duplicate check and the rename happen, so two uploads
# with the same name cannot both pass the check and then overwrite each other.
# One lock protects one server process (this project runs a single process);
# several processes would need a different mechanism, which is out of scope.
_STORE_LOCK = threading.Lock()

# Names Windows refuses to use as a file name (with any extension).
_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{base}{n}" for base in ("COM", "LPT") for n in range(1, 10)
}

# Status for each way the loader can reject a PDF.
_LOAD_ERROR_STATUS = {
    pdf_loader.EMPTY: 400,
    pdf_loader.CORRUPT: 400,
    pdf_loader.ENCRYPTED: 400,
    pdf_loader.NO_PAGES: 400,
    pdf_loader.NO_TEXT: 422,
}


class UploadRejected(Exception):
    """Internal: stops processing of one file with the HTTP status to report."""

    def __init__(
        self, status_code: int, message: str, over_limit: list[OverLimitChunk] | None = None,
        max_chunk_tokens: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.over_limit = over_limit
        self.max_chunk_tokens = max_chunk_tokens


def sanitize_filename(raw_name: str) -> str:
    """Turn a client-supplied name into a safe base name for the uploads folder.

    The name is first normalized to Unicode NFC, so `Cafe` + combining accent
    and the single character `Café` become the same name. Then:

    - any directory part is dropped (both / and \\ separators, so
      `../../x.pdf` and `C:\\temp\\x.pdf` become `x.pdf`);
    - letters, combining marks and numbers of any script are kept (Hindi,
      Urdu, Arabic with diacritics, Japanese, Korean ...), as are `.`, `-`,
      `_` and space; every other character, including control and
      direction-override characters, becomes `_`;
    - Windows device names (CON, NUL, COM1 ...) get a `_` prefix;
    - the length is limited in characters and in UTF-8 bytes.

    Returns "" if nothing usable is left.
    """
    name = unicodedata.normalize("NFC", raw_name).replace("\\", "/").split("/")[-1]
    name = "".join(ch if _is_allowed_char(ch) else "_" for ch in name).strip(" .")
    if not name:
        return ""
    stem, dot, extension = name.rpartition(".")
    if not dot:  # no extension at all
        stem, extension = name, ""
    if stem.split(".")[0].upper() in _WINDOWS_RESERVED:  # CON.txt is reserved too
        stem = f"_{stem}"
    extension = f".{extension}" if extension else ""
    stem = _shorten(stem, extension).rstrip(" .")
    return f"{stem}{extension}" if stem else ""


def _is_allowed_char(char: str) -> bool:
    # Unicode categories: L = letters, M = combining marks (needed by Hindi,
    # Arabic diacritics and decomposed accents), N = numbers.
    return char in ".-_ " or unicodedata.category(char)[0] in "LMN"


def _shorten(stem: str, extension: str) -> str:
    """Cut the stem so the whole name fits both length limits."""
    stem = stem[: max(MAX_NAME_LENGTH - len(extension), 1)]
    byte_budget = MAX_NAME_BYTES - len(extension.encode("utf-8"))
    while len(stem) > 1 and len(stem.encode("utf-8")) > byte_budget:
        stem = stem[:-1]
    return stem


@router.post("", response_model=UploadResponse)
def upload_documents(
    files: Annotated[list[UploadFile], File(description="One or more PDF files")],
    response: Response,
) -> UploadResponse:
    """Upload PDFs and return, per file, the extracted page information.

    HTTP status: 200 if at least one file was accepted. If every file was
    rejected, the status of the first rejected file is used (so a single-file
    upload gets exactly its own status). `results` always has one entry per file.
    """
    uploads_dir = Path(settings.uploads_dir)
    results = [_process_upload(upload, uploads_dir) for upload in files]

    if not any(result.success for result in results):
        response.status_code = results[0].status_code
    return UploadResponse(results=results)


def _process_upload(upload: UploadFile, uploads_dir: Path) -> FileResult:
    original_name = upload.filename or ""
    safe_name = sanitize_filename(original_name)
    try:
        return _accept(upload, original_name, safe_name, uploads_dir)
    except UploadRejected as rejected:
        logger.warning(
            "Rejected upload %r (%d): %s", original_name, rejected.status_code, rejected.message
        )
        return FileResult(
            original_name=original_name,
            file_name=safe_name or None,
            success=False,
            status_code=rejected.status_code,
            error=rejected.message,
            over_limit_chunks=rejected.over_limit,
            max_chunk_tokens=rejected.max_chunk_tokens,
        )
    except Exception:  # one bad file must never break the others
        logger.exception("Unexpected error while processing upload %r", original_name)
        return FileResult(
            original_name=original_name,
            file_name=safe_name or None,
            success=False,
            status_code=500,
            error="Unexpected error while processing this file.",
        )


def _accept(
    upload: UploadFile, original_name: str, safe_name: str, uploads_dir: Path
) -> FileResult:
    if not safe_name:
        raise UploadRejected(400, "The file name is missing or has no usable characters.")
    if not safe_name.lower().endswith(".pdf"):
        raise UploadRejected(415, "Only .pdf files are accepted.")
    if _name_exists(uploads_dir, safe_name):
        raise UploadRejected(
            409, f"A document named {safe_name!r} already exists; it was not changed."
        )

    uploads_dir.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=_TEMP_PREFIX, suffix=_TEMP_SUFFIX, dir=uploads_dir
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as temp_file:
            _copy_with_limit(upload, temp_file, settings.max_upload_bytes)
        pages = _load(temp_path, safe_name)
        # Slow part (model): chunk, check token limits, embed. Outside the lock.
        prepared = _prepare(pages, safe_name)

        # Checked again just before the move, and under a lock: another request
        # may have used the name while this file was being processed, and
        # os.replace would silently overwrite it. Check, index and move are one step.
        with _STORE_LOCK:
            if _name_exists(uploads_dir, safe_name):
                raise UploadRejected(
                    409,
                    f"A document named {safe_name!r} already exists; it was not changed.",
                )
            pipeline.store_document(prepared)  # removes its own partial chunks on failure
            try:
                os.replace(temp_path, uploads_dir / safe_name)  # atomic on one filesystem
            except Exception:
                _remove_chunks_quietly(safe_name)  # no PDF -> no chunks (no orphans)
                raise
    finally:
        temp_path.unlink(missing_ok=True)  # no-op after a successful move

    blank_pages = [page.page_number for page in pages if not page.text]
    logger.info(
        "Accepted %s: %d pages (%d blank)", safe_name, len(pages), len(blank_pages)
    )
    return FileResult(
        original_name=original_name,
        file_name=safe_name,
        success=True,
        status_code=200,
        page_count=len(pages),
        blank_pages=blank_pages,
        chunk_count=prepared.chunk_count,
        max_chunk_tokens=prepared.max_chunk_tokens,
        pages=[
            PagePreview(
                page_number=page.page_number,
                char_count=len(page.text),
                preview=" ".join(page.text.split())[:PREVIEW_CHARS],
            )
            for page in pages
        ],
    )


def _prepare(pages: list[pdf_loader.PageText], file_name: str) -> pipeline.PreparedDocument:
    try:
        return pipeline.prepare_document(file_name, pages)
    except pipeline.ChunksOverTokenLimit as error:
        raise UploadRejected(
            422,
            str(error),
            over_limit=[OverLimitChunk(chunk_id=c, token_count=n) for c, n in error.over_limit],
            max_chunk_tokens=error.max_chunk_tokens,
        ) from error


def _remove_chunks_quietly(file_name: str) -> None:
    try:
        vector_store.delete_file_chunks(
            Path(settings.chroma_dir), settings.chroma_collection_name, file_name
        )
    except Exception:
        logger.exception("Could not remove chunks of %s; run rebuild_index()", file_name)


def _stored_pdfs(uploads_dir: Path) -> list[Path]:
    """Finished PDFs only: temp `.upload-*.part` files and other files are ignored."""
    if not uploads_dir.is_dir():
        return []
    return sorted(
        (e for e in uploads_dir.iterdir() if e.is_file() and e.suffix.lower() == ".pdf"),
        key=lambda e: e.name.lower(),
    )


@router.get("", response_model=DocumentList)
def list_documents() -> DocumentList:
    """Uploaded PDFs with their indexing status, plus indexed names with no PDF."""
    pdfs = _stored_pdfs(Path(settings.uploads_dir))
    counts = vector_store.read_file_chunk_counts(
        Path(settings.chroma_dir), settings.chroma_collection_name
    )
    on_disk = {p.name for p in pdfs}
    return DocumentList(
        documents=[
            DocumentInfo(
                file_name=p.name,
                size_bytes=p.stat().st_size,
                indexed=counts.get(p.name, 0) > 0,
                chunk_count=counts.get(p.name, 0),
            )
            for p in pdfs
        ],
        orphan_files=sorted(set(counts) - on_disk),
    )


@router.delete("/{file_name}", response_model=DeleteResponse)
def delete_document(file_name: str) -> DeleteResponse:
    """Delete a PDF and its chunks. Chunks go FIRST: if removing the file then
    fails, the PDF merely shows as 'not indexed' (fixable by a rebuild), whereas
    the reverse order could leave chunks that cite a file that no longer exists."""
    wanted = sanitize_filename(file_name).lower()
    with _STORE_LOCK:
        # The stored name comes from the disk listing; the user's string never
        # becomes part of a path.
        match = next((p for p in _stored_pdfs(Path(settings.uploads_dir)) if p.name.lower() == wanted), None)
        if not wanted or match is None:
            raise HTTPException(status_code=404, detail=f"No document named {file_name!r}.")
        removed = vector_store.delete_file_chunks(
            Path(settings.chroma_dir), settings.chroma_collection_name, match.name
        )
        match.unlink()
        _SUGGESTIONS_CACHE.pop(match.name, None)
    logger.info("Deleted %s (%d chunks)", match.name, removed)
    return DeleteResponse(file_name=match.name, chunks_removed=removed)


def _name_exists(uploads_dir: Path, name: str) -> bool:
    """Case-insensitive, because Windows and macOS treat A.pdf and a.pdf as one file."""
    if not uploads_dir.is_dir():
        return False
    wanted = name.lower()
    return any(entry.name.lower() == wanted for entry in uploads_dir.iterdir())


def _copy_with_limit(upload: UploadFile, destination, max_bytes: int) -> None:
    """Copy the upload piece by piece; stop as soon as it proves too large,
    empty, or not a PDF."""
    total = 0
    header = b""
    while True:
        chunk = upload.file.read(CHUNK_SIZE)
        if not chunk:
            break
        if len(header) < len(PDF_MAGIC):
            header = (header + chunk)[: len(PDF_MAGIC)]
        total += len(chunk)
        if total > max_bytes:
            raise UploadRejected(
                413, f"The file is larger than the {settings.max_upload_mb} MB limit."
            )
        destination.write(chunk)

    if total == 0:
        raise UploadRejected(400, "The file is empty.")
    if header != PDF_MAGIC:
        raise UploadRejected(415, "The file is not a PDF (missing %PDF- header).")


def _load(path: Path, file_name: str) -> list[pdf_loader.PageText]:
    try:
        return extract_pages(path, file_name)
    except PdfLoadError as error:
        raise UploadRejected(_LOAD_ERROR_STATUS[error.reason], error.message) from error


_SUGGESTIONS_CACHE: dict[str, list[str]] = {}


@router.get("/{file_name}/suggestions")
def get_document_suggestions(file_name: str) -> dict[str, Any]:
    """Return 4 grounded suggestion questions for a ready document."""
    clean_name = sanitize_filename(file_name)
    if clean_name in _SUGGESTIONS_CACHE:
        return {"file_name": clean_name, "suggestions": _SUGGESTIONS_CACHE[clean_name]}

    uploads_dir = Path(settings.uploads_dir)
    sample_dir = uploads_dir.parent / "sample_pdfs"

    match = None
    if uploads_dir.is_dir():
        for entry in uploads_dir.iterdir():
            if entry.name.lower() == clean_name.lower():
                match = entry
                break
    if match is None and sample_dir.is_dir():
        for entry in sample_dir.iterdir():
            if entry.name.lower() == clean_name.lower():
                match = entry
                break

    if match is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    suggestions: list[str] = []
    try:
        pages = extract_pages(match, match.name)
        text_sample = " ".join(p.text for p in pages[:2])[:1500]
        if text_sample.strip():
            from backend.generation.llm_client import GroqClient
            client = GroqClient()
            prompt = (
                "Based on this document excerpt, provide exactly 4 short, specific, useful questions that a reader would ask.\n"
                "Each question must be under 70 characters, in sentence case, in plain language, ending with a question mark.\n"
                "Output each question on its own line without numbering, bullets, or extra text.\n\n"
                f"Excerpt:\n{text_sample}"
            )
            raw = client.generate([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=150)
            lines = [line.strip().lstrip("0123456789.-*• ") for line in raw.splitlines() if line.strip()]
            for q in lines:
                if q and len(q) <= 75 and q.endswith("?"):
                    suggestions.append(q)
                if len(suggestions) == 4:
                    break
    except Exception as exc:
        logger.info("Dynamic LLM suggestion generation unavailable for %s: %s", match.name, exc)

    if len(suggestions) < 4:
        fn_lower = match.name.lower()
        if "hr" in fn_lower or "policy" in fn_lower:
            fallbacks = [
                "What is the annual leave allowance?",
                "How are travel expenses reimbursed?",
                "What are the remote work guidelines?",
                "What is the policy for medical leave?",
            ]
        elif "spec" in fn_lower or "product" in fn_lower:
            fallbacks = [
                "What are the system specifications?",
                "What are the power and battery ratings?",
                "What interfaces and ports are supported?",
                "What is the standard warranty coverage?",
            ]
        elif "brief" in fn_lower or "intern" in fn_lower or "rag" in fn_lower:
            fallbacks = [
                "What are the core project objectives?",
                "What are the groundedness and citation rules?",
                "What items are designated out of scope?",
                "What are the key testing requirements?",
            ]
        else:
            fallbacks = [
                f"What are the key provisions in {match.name}?",
                "What requirements and deadlines are outlined?",
                "Explain the main policies and guidelines",
                "What responsibilities are defined here?",
            ]
        for fb in fallbacks:
            if fb not in suggestions:
                suggestions.append(fb)
            if len(suggestions) == 4:
                break

    _SUGGESTIONS_CACHE[clean_name] = suggestions[:4]
    return {"file_name": clean_name, "suggestions": _SUGGESTIONS_CACHE[clean_name]}
