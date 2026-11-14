"""Page-level text extraction from digital PDFs (PyMuPDF).

The rest of the pipeline cites sources as "file X, page N", so the one rule of
this module is: **`page_number` is the physical page position in the PDF,
1-based** (the first page is 1). PyMuPDF counts from 0; we add 1 in exactly one
place. Blank pages keep their number, so page 5 is always page 5.

Scanned (image-only) PDFs contain no text; reading them needs OCR, which is out
of scope, so they are rejected with a clear error.
"""

import gc
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)

# PyMuPDF's documentation says it does not support multiple threads ("may cause
# incorrect behaviour or even crash Python"). The upload endpoint is a plain
# `def`, so FastAPI runs it in a thread pool and two uploads can reach this
# module at the same time. This lock lets only one thread use PyMuPDF at once.
# It protects one process; it is not shared between several server processes.
_PYMUPDF_LOCK = threading.Lock()

# Reasons carried by PdfLoadError, so callers can react without parsing messages.
EMPTY = "empty"
CORRUPT = "corrupt"
ENCRYPTED = "encrypted"
NO_PAGES = "no_pages"
NO_TEXT = "no_text"


@dataclass(frozen=True)
class PageText:
    """The text of one PDF page, with the metadata every citation needs."""

    file_name: str
    page_number: int  # physical page, 1-based
    text: str  # stripped; empty string for a blank page


class PdfLoadError(Exception):
    """The PDF cannot be used. `reason` is one of the module constants above."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def extract_pages(path: str | Path, file_name: str) -> list[PageText]:
    """Return one PageText per physical page of the PDF at `path`.

    `file_name` is the name to record in the metadata (the stored upload name),
    which may differ from the name of a temporary file on disk.

    Raises PdfLoadError for an empty, corrupt, encrypted, zero-page or
    text-less (scanned) PDF.
    """
    # Opening, reading and closing the document all happen under the lock, so
    # no two threads are ever inside PyMuPDF together. Only this block is
    # locked; the rest of the upload (saving, size checks) runs in parallel.
    with _PYMUPDF_LOCK:
        pages = _read_pages(path, file_name)

    if not any(page.text for page in pages):
        raise PdfLoadError(
            NO_TEXT,
            "The PDF has no extractable text. It looks scanned or image-only; "
            "OCR is not supported.",
        )

    logger.debug("Extracted %d pages from %s", len(pages), file_name)
    return pages


def _read_pages(path: str | Path, file_name: str) -> list[PageText]:
    """Open the PDF, read every page and close it. Callers must hold
    `_PYMUPDF_LOCK`."""
    doc = None
    open_error: str | None = None
    try:
        doc = pymupdf.open(path, filetype="pdf")
    except pymupdf.EmptyFileError:
        open_error = EMPTY
    except Exception:  # PyMuPDF raises several types for broken files
        open_error = CORRUPT

    if open_error is not None:
        # Force garbage collection outside the except block so PyMuPDF's
        # internal C file stream (fz_stream) is closed on Windows before
        # raising, allowing callers to delete or move the temporary file.
        gc.collect()
        if open_error == EMPTY:
            raise PdfLoadError(EMPTY, "The file is empty.")
        raise PdfLoadError(CORRUPT, "The file is not a readable PDF.")

    with doc:
        if doc.needs_pass:
            raise PdfLoadError(
                ENCRYPTED, "The PDF is password-protected and cannot be read."
            )
        if doc.page_count == 0:
            raise PdfLoadError(NO_PAGES, "The PDF has no pages.")

        return [
            PageText(
                file_name=file_name,
                page_number=index + 1,  # PyMuPDF is 0-based; citations are 1-based
                text=_clean(page.get_text("text")),
            )
            for index, page in enumerate(doc)
        ]


def _clean(text: str) -> str:
    """Remove NUL characters and surrounding whitespace."""
    return text.replace("\x00", "").strip()
