"""Shared test helpers. PDFs are generated in code; nothing is read from disk
fixtures and nothing is written outside pytest's temporary directories."""

import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _TESTS_DIR.parent
_REPO_ROOT = _BACKEND_DIR.parent
for _p in [str(_REPO_ROOT), str(_BACKEND_DIR), str(_TESTS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend.api import documents
from backend.config import settings
from backend.ingestion import pdf_loader
from backend.main import app
from backend.retrieval import services
from tests.mocks.fake_embedder import FakeEmbedder


@pytest.fixture(autouse=True)
def isolated_uploads_dir(tmp_path, monkeypatch):
    """Point the app at temporary uploads and sample folders for every test, so no test
    can touch the real data directories."""
    uploads = tmp_path / "uploads"
    samples = tmp_path / "sample_pdfs"
    monkeypatch.setattr(settings, "uploads_dir", uploads)
    monkeypatch.setattr(settings, "sample_dir", samples)
    return uploads


@pytest.fixture(scope="session", autouse=True)
def real_chroma_folder_must_stay_untouched():
    """D-008: no test may write to the real data/chroma folder. A stray
    `chroma.sqlite3` there was seen once during Stage 3 and could not be
    reproduced; this guard turns any repeat into a failing run."""
    from backend.config import DATA_DIR

    database = DATA_DIR / "chroma" / "chroma.sqlite3"
    existed_before = database.exists()
    yield
    if not existed_before and database.exists():
        pytest.fail(f"a test wrote to the real Chroma folder: {database}")


@pytest.fixture(scope="session", autouse=True)
def real_conversations_db_must_stay_untouched():
    """No test may write to or modify the real data/conversations.db file."""
    from backend.config import DATA_DIR

    database = DATA_DIR / "conversations.db"
    size_before = database.stat().st_size if database.exists() else None
    yield
    if database.exists():
        if size_before is None:
            pytest.fail(f"a test created the real conversations DB: {database}")
        elif database.stat().st_size != size_before:
            pytest.fail(f"a test modified the real conversations DB: {database}")


@pytest.fixture(autouse=True)
def isolated_conversations_db(tmp_path, monkeypatch):
    """Every test gets a temporary conversations DB, preventing writes to data/conversations.db."""
    from backend.conversation import store as conv_store

    temp_db = tmp_path / "conversations.db"
    monkeypatch.setattr(settings, "conversations_db_path", temp_db)
    conv_store.set_conversation_store(None)
    yield
    conv_store.set_conversation_store(None)


@pytest.fixture(autouse=True)
def isolated_chroma(tmp_path, monkeypatch):
    """Every test gets a temp Chroma folder and a FakeEmbedder: no test loads a
    real model or touches data/chroma."""
    monkeypatch.setattr(settings, "chroma_dir", tmp_path / "chroma")
    monkeypatch.setattr(settings, "token_aware_chunking", False)
    services.reset_caches()
    services.set_embedder_override(FakeEmbedder())
    yield
    services.reset_caches()


@pytest.fixture(autouse=True)
def locks_must_be_free_after_each_test():
    """Turn a leaked lock into a clear failure of the test that leaked it.

    If code forgot to release one of the locks (for example after an error),
    the next test that needs it would wait forever and freeze the whole run.
    This check never waits: it looks at the lock right after each test, and if
    it is still held it releases it (so later tests can run) and fails the
    test that caused the leak.
    """
    yield
    leaked = []
    for name, lock in (
        ("_PYMUPDF_LOCK", pdf_loader._PYMUPDF_LOCK),
        ("_STORE_LOCK", documents._STORE_LOCK),
    ):
        if not lock.acquire(blocking=False):
            leaked.append(name)
        lock.release()  # frees a leaked lock, or the one just acquired
    if leaked:
        pytest.fail(f"lock still held after the test (leaked): {', '.join(leaked)}")


@pytest.fixture
def client():
    return TestClient(app)


def _pdf_bytes(page_texts: list[str | None], **save_options) -> bytes:
    doc = pymupdf.open()
    for text in page_texts:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    return doc.tobytes(**save_options)


@pytest.fixture
def make_pdf():
    """make_pdf(["text of page 1", None, "text of page 3"]) -> PDF bytes.
    None (or "") produces a blank page."""
    return _pdf_bytes


@pytest.fixture
def make_image_only_pdf():
    """A PDF whose only content is a picture (like a scan): no text at all."""

    def build() -> bytes:
        doc = pymupdf.open()
        page = doc.new_page()
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 80), False)
        pixmap.clear_with(180)
        page.insert_image(pymupdf.Rect(72, 72, 200, 200), pixmap=pixmap)
        return doc.tobytes()

    return build


@pytest.fixture
def make_encrypted_pdf():
    """A PDF that needs a password to open."""

    def build() -> bytes:
        return _pdf_bytes(
            ["secret"],
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            user_pw="user-password",
            owner_pw="owner-password",
        )

    return build
