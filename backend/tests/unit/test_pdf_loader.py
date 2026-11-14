import threading
import time

import pymupdf
import pytest

from backend.ingestion import pdf_loader
from backend.ingestion.pdf_loader import PageText, PdfLoadError, extract_pages


@pytest.fixture
def write_file(tmp_path):
    def write(name: str, content: bytes):
        path = tmp_path / name
        path.write_bytes(content)
        return path

    return write


def test_three_pages_with_different_text_map_to_the_right_page_numbers(
    make_pdf, write_file
):
    path = write_file(
        "guide.pdf",
        make_pdf(["alpha first page", "bravo second page", "charlie third page"]),
    )

    pages = extract_pages(path, "guide.pdf")

    assert [p.page_number for p in pages] == [1, 2, 3]  # physical, 1-based
    assert "alpha" in pages[0].text and "bravo" not in pages[0].text
    assert "bravo" in pages[1].text and "charlie" not in pages[1].text
    assert "charlie" in pages[2].text and "alpha" not in pages[2].text
    assert all(isinstance(p, PageText) for p in pages)
    assert {p.file_name for p in pages} == {"guide.pdf"}


def test_file_name_comes_from_the_argument_not_from_the_path(make_pdf, write_file):
    path = write_file("tmp-upload.part", make_pdf(["hello"]))

    pages = extract_pages(path, "Handbook.pdf")

    assert pages[0].file_name == "Handbook.pdf"


def test_blank_pages_keep_their_physical_numbers(make_pdf, write_file):
    path = write_file("gaps.pdf", make_pdf(["one", None, "three", ""]))

    pages = extract_pages(path, "gaps.pdf")

    assert [p.page_number for p in pages] == [1, 2, 3, 4]
    assert [bool(p.text) for p in pages] == [True, False, True, False]
    assert pages[2].text == "three"  # not shifted onto page 2


def test_whitespace_only_page_counts_as_blank(make_pdf, write_file):
    path = write_file("ws.pdf", make_pdf(["real text", "   "]))

    pages = extract_pages(path, "ws.pdf")

    assert pages[1].text == ""


def test_image_only_pdf_is_rejected_as_no_text(make_image_only_pdf, write_file):
    path = write_file("scan.pdf", make_image_only_pdf())

    with pytest.raises(PdfLoadError) as error:
        extract_pages(path, "scan.pdf")

    assert error.value.reason == pdf_loader.NO_TEXT
    assert "OCR" in error.value.message


def test_pdf_with_only_blank_pages_is_rejected_as_no_text(make_pdf, write_file):
    path = write_file("blank.pdf", make_pdf([None, None]))

    with pytest.raises(PdfLoadError) as error:
        extract_pages(path, "blank.pdf")

    assert error.value.reason == pdf_loader.NO_TEXT


def test_encrypted_pdf_is_rejected(make_encrypted_pdf, write_file):
    path = write_file("locked.pdf", make_encrypted_pdf())

    with pytest.raises(PdfLoadError) as error:
        extract_pages(path, "locked.pdf")

    assert error.value.reason == pdf_loader.ENCRYPTED


def test_pdf_with_only_an_owner_password_is_readable(make_pdf, write_file):
    # An owner password restricts editing/printing but needs no password to open,
    # so the text can be read and the file is accepted.
    content = make_pdf(
        ["readable text"],
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner-password",
        user_pw="",
    )
    path = write_file("owner-only.pdf", content)

    pages = extract_pages(path, "owner-only.pdf")

    assert pages[0].text == "readable text"


def test_empty_file_is_rejected(write_file):
    path = write_file("empty.pdf", b"")

    with pytest.raises(PdfLoadError) as error:
        extract_pages(path, "empty.pdf")

    assert error.value.reason == pdf_loader.EMPTY


def test_corrupt_file_is_rejected(write_file):
    path = write_file("broken.pdf", b"%PDF-1.4\nthis is not a real pdf body\n")

    with pytest.raises(PdfLoadError) as error:
        extract_pages(path, "broken.pdf")

    assert error.value.reason == pdf_loader.CORRUPT


def test_corrupt_file_releases_handle_so_file_can_be_deleted(write_file):
    # Regression test for Windows: PyMuPDF failed open must release file handle
    # so that callers can delete temporary files without PermissionError [WinError 32].
    path = write_file("broken_handle.pdf", b"%PDF-1.4\ncorrupt body\n")

    with pytest.raises(PdfLoadError):
        extract_pages(path, "broken_handle.pdf")

    path.unlink()
    assert not path.exists()


def test_plain_text_file_is_rejected_as_corrupt(write_file):
    path = write_file("notes.pdf", b"just some text, not a PDF\n")

    with pytest.raises(PdfLoadError) as error:
        extract_pages(path, "notes.pdf")

    assert error.value.reason == pdf_loader.CORRUPT


def test_pdf_with_zero_pages_is_rejected(write_file):
    # A hand-written PDF whose page tree is empty. PyMuPDF cannot create one.
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"trailer\n<< /Root 1 0 R /Size 3 >>\n%%EOF\n"
    )
    path = write_file("nopages.pdf", body)

    with pytest.raises(PdfLoadError) as error:
        extract_pages(path, "nopages.pdf")

    # Verified with PyMuPDF 1.28.0 and 1.28.2: the file opens, reports zero
    # pages, and is refused as NO_PAGES (not as CORRUPT).
    assert error.value.reason == pdf_loader.NO_PAGES
    assert error.value.message == "The PDF has no pages."


# --- thread safety (PyMuPDF does not support concurrent threads) ------------


class _Tracker:
    """Counts how many threads are inside PyMuPDF at the same moment, and
    records whether the PyMuPDF lock was held at each step."""

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.phases_without_lock: list[str] = []
        self.phases_seen: set[str] = set()

    def enter(self) -> None:
        with self._guard:
            self.active += 1
            self.max_active = max(self.max_active, self.active)

    def leave(self) -> None:
        with self._guard:
            self.active -= 1

    def check_lock(self, phase: str) -> None:
        with self._guard:
            self.phases_seen.add(phase)
            if not pdf_loader._PYMUPDF_LOCK.locked():
                self.phases_without_lock.append(phase)


class _TrackedDocument:
    """Wraps a real PyMuPDF document. From the moment the document is opened
    until it is closed it counts as 'inside PyMuPDF'. Reading each page and
    closing the document are slowed down, so that a thread that has left the
    lock too early would overlap with another thread."""

    def __init__(self, document, tracker: _Tracker) -> None:
        self._document = document
        self._tracker = tracker
        tracker.enter()
        tracker.check_lock("open")

    @property
    def needs_pass(self):
        return self._document.needs_pass

    @property
    def page_count(self):
        return self._document.page_count

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self._tracker.check_lock("close")
        self._document.close()
        time.sleep(0.02)  # still 'inside PyMuPDF' for a moment after close()
        self._tracker.leave()

    def __iter__(self):
        for page in self._document:
            self._tracker.check_lock("read")
            time.sleep(0.02)
            yield page


@pytest.fixture
def track_pymupdf(monkeypatch):
    """Call it AFTER building the test PDF (make_pdf itself uses pymupdf.open):
    from then on pdf_loader opens every PDF through a _TrackedDocument.
    Returns the _Tracker."""

    def install() -> _Tracker:
        tracker = _Tracker()
        real_open = pymupdf.open
        monkeypatch.setattr(
            pdf_loader.pymupdf,
            "open",
            lambda *args, **kwargs: _TrackedDocument(
                real_open(*args, **kwargs), tracker
            ),
        )
        return tracker

    return install


def _run_in_threads(target, count: int) -> list[BaseException]:
    """Start `count` threads together; return the exceptions they raised."""
    barrier = threading.Barrier(count)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            barrier.wait(timeout=10)
            target()
        except BaseException as exc:  # noqa: BLE001 - reported to the test
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return errors


def test_lock_is_held_while_opening_reading_and_closing(
    write_file, make_pdf, track_pymupdf
):
    # Deterministic, single thread: the lock must be held at every PyMuPDF step,
    # including close(). If close() ran after the lock was released, another
    # thread could be inside PyMuPDF at the same time.
    path = write_file("steps.pdf", make_pdf(["one", "two"]))
    tracker = track_pymupdf()

    extract_pages(path, "steps.pdf")

    assert tracker.phases_seen == {"open", "read", "close"}  # every step was observed
    assert tracker.phases_without_lock == []


def test_concurrent_extractions_never_overlap_inside_pymupdf(
    make_pdf, write_file, track_pymupdf
):
    path = write_file("busy.pdf", make_pdf(["one", "two", "three"]))
    tracker = track_pymupdf()
    results: list[list[PageText]] = []

    errors = _run_in_threads(
        lambda: results.append(extract_pages(path, "busy.pdf")), count=8
    )

    assert errors == []
    assert len(results) == 8
    assert all([p.page_number for p in pages] == [1, 2, 3] for pages in results)
    assert tracker.max_active == 1  # serialized: never two threads at once
    assert tracker.phases_without_lock == []


def test_lock_is_released_after_an_error(write_file, make_pdf):
    # A failing extraction must not leave the lock held (that would freeze
    # every later upload).
    broken = write_file("broken.pdf", b"%PDF-1.4\nnot a real pdf body\n")
    good = write_file("good.pdf", make_pdf(["still works"]))

    with pytest.raises(PdfLoadError):
        extract_pages(broken, "broken.pdf")

    # Check the lock first without waiting: a leaked lock would otherwise make
    # the next extract_pages call hang forever instead of failing the test.
    assert pdf_loader._PYMUPDF_LOCK.acquire(blocking=False), "lock was leaked"
    pdf_loader._PYMUPDF_LOCK.release()
    assert extract_pages(good, "good.pdf")[0].text == "still works"
