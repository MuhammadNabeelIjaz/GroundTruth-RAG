import pytest

from backend.config import settings
from backend.ingestion import pipeline
from backend.ingestion.pdf_loader import PageText
from backend.ingestion.pipeline import ChunksOverTokenLimit
from backend.retrieval import services
from tests.mocks.fake_embedder import FakeEmbedder


def pages(name="doc.pdf", texts=("Annual leave is 20 days.", "Sick leave is 10 days.")):
    return [PageText(name, i + 1, t) for i, t in enumerate(texts)]


def test_ingest_stores_every_chunk_with_page_metadata():
    prepared = pipeline.ingest_pages("doc.pdf", pages())
    store = services.get_store()
    assert prepared.chunk_count == 2 and store.count() == 2
    top = store.query(services.get_embedder().embed_query("Sick leave is 10 days."), 1)[0]
    assert (top.file_name, top.page_number, top.chunk_id) == ("doc.pdf", 2, "doc.pdf:2:0")
    assert prepared.max_chunk_tokens == services.get_embedder().count_tokens("Annual leave is 20 days.")


def test_reingesting_replaces_old_chunks():
    pipeline.ingest_pages("doc.pdf", pages(texts=("first one", "second one", "third one")))
    pipeline.ingest_pages("doc.pdf", pages(texts=("only page",)))
    store = services.get_store()
    assert store.count() == 1 and store.file_chunk_counts() == {"doc.pdf": 1}


def test_blank_pages_only_stores_nothing():
    prepared = pipeline.ingest_pages("doc.pdf", [PageText("doc.pdf", 1, "")])
    assert prepared.chunk_count == 0 and prepared.max_chunk_tokens == 0
    assert services.get_store().count() == 0


def test_over_limit_chunk_is_never_embedded_or_stored():
    fake = FakeEmbedder(max_tokens=20)
    services.set_embedder_override(fake)
    long_text = " ".join(f"w{i}" for i in range(60))  # one 400+ char chunk, ~62 tokens
    with pytest.raises(ChunksOverTokenLimit) as info:
        pipeline.ingest_pages("doc.pdf", pages(texts=("short text", long_text)))
    assert info.value.over_limit[0][0] == "doc.pdf:2:0"
    assert info.value.max_chunk_tokens == info.value.over_limit[0][1] > 20
    assert fake.document_calls == []
    assert services.get_store().count() == 0
    assert "Nothing was stored" in str(info.value)


def test_token_aware_pipeline_safely_ingests_dense_document():
    fake = FakeEmbedder(max_tokens=20)
    services.set_embedder_override(fake)
    long_text = " ".join(f"w{i}" for i in range(60))  # 60 words
    prepared = pipeline.ingest_pages("doc.pdf", pages(texts=("short text", long_text)), token_aware=True)
    assert prepared.chunk_count > 1
    assert prepared.max_chunk_tokens <= 20
    assert services.get_store().count() == prepared.chunk_count


def test_embedding_happens_in_batches(monkeypatch):
    monkeypatch.setattr(settings, "embedding_batch_size", 2)
    fake = services.get_embedder()
    pipeline.ingest_pages("doc.pdf", pages(texts=tuple(f"page {i} text" for i in range(5))))
    assert [len(c) for c in fake.document_calls] == [2, 2, 1]
    assert services.get_store().count() == 5


def test_embedding_failure_stores_nothing(monkeypatch):
    def boom(self, texts, *, is_query):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(FakeEmbedder, "_encode", boom)
    with pytest.raises(RuntimeError):
        pipeline.ingest_pages("doc.pdf", pages())
    assert services.get_store().count() == 0


def test_failed_store_write_removes_partial_chunks(monkeypatch):
    store = services.get_store()
    real_upsert = store.upsert_chunks
    calls = []

    def write_then_fail(**kwargs):
        calls.append(1)
        real_upsert(**kwargs)  # the write itself lands...
        raise RuntimeError("disk full")  # ...then reports failure

    monkeypatch.setattr(store, "upsert_chunks", lambda **kw: write_then_fail(**kw))
    with pytest.raises(RuntimeError, match="disk full"):
        pipeline.ingest_pages("doc.pdf", pages())
    assert calls and store.count() == 0


def test_failed_cleanup_is_logged_not_raised(monkeypatch, caplog):
    store = services.get_store()
    monkeypatch.setattr(store, "upsert_chunks", lambda **kw: (_ for _ in ()).throw(RuntimeError("write failed")))
    calls = []

    def delete(name):
        calls.append(name)
        if len(calls) > 1:
            raise OSError("cleanup failed")

    monkeypatch.setattr(store, "delete_file", delete)
    with pytest.raises(RuntimeError, match="write failed"):  # original error wins
        pipeline.ingest_pages("doc.pdf", pages())
    assert "rebuild_index" in caplog.text


def test_other_files_are_untouched_by_ingest():
    pipeline.ingest_pages("a.pdf", pages("a.pdf"))
    pipeline.ingest_pages("b.pdf", pages("b.pdf"))
    pipeline.ingest_pages("a.pdf", pages("a.pdf", texts=("new",)))
    assert services.get_store().file_chunk_counts() == {"a.pdf": 1, "b.pdf": 2}


# ---- rebuild_index --------------------------------------------------------


def test_rebuild_indexes_every_pdf_and_removes_orphans(make_pdf, isolated_uploads_dir):
    isolated_uploads_dir.mkdir()
    (isolated_uploads_dir / "a.pdf").write_bytes(make_pdf(["alpha text", "beta text"]))
    (isolated_uploads_dir / "b.PDF").write_bytes(make_pdf(["gamma text"]))
    (isolated_uploads_dir / ".upload-x.part").write_bytes(b"junk")
    (isolated_uploads_dir / "notes.txt").write_text("ignore me")
    pipeline.ingest_pages("gone.pdf", pages("gone.pdf"))  # orphan: no PDF on disk

    report = pipeline.rebuild_index()

    assert report.indexed == {"a.pdf": 2, "b.PDF": 1} and report.failed == {}
    store = services.get_store()
    assert store.file_chunk_counts() == {"a.pdf": 2, "b.PDF": 1}
    assert store.verify_index({"a.pdf", "b.PDF"}) == []


def test_rebuild_reports_failures_and_continues(make_pdf, isolated_uploads_dir, monkeypatch):
    isolated_uploads_dir.mkdir()
    (isolated_uploads_dir / "good.pdf").write_bytes(make_pdf(["fine text"]))
    (isolated_uploads_dir / "corrupt.pdf").write_bytes(b"%PDF-1.4 not really")
    (isolated_uploads_dir / "long.pdf").write_bytes(make_pdf(["placeholder"]))
    services.set_embedder_override(FakeEmbedder(max_tokens=30))
    real = pipeline.extract_pages
    long_text = " ".join(f"w{i}" for i in range(80))  # ~82 tokens, one chunk

    def extract(path, name):
        # a one-line test PDF is clipped by the page edge, so inject the long text
        return [PageText(name, 1, long_text)] if name == "long.pdf" else real(path, name)

    monkeypatch.setattr(pipeline, "extract_pages", extract)

    report = pipeline.rebuild_index()

    assert report.indexed == {"good.pdf": 1}
    assert set(report.failed) == {"corrupt.pdf", "long.pdf"}
    assert "token" in report.failed["long.pdf"]


def test_rebuild_survives_an_unexpected_error(make_pdf, isolated_uploads_dir, monkeypatch):
    isolated_uploads_dir.mkdir()
    (isolated_uploads_dir / "a.pdf").write_bytes(make_pdf(["alpha"]))
    (isolated_uploads_dir / "b.pdf").write_bytes(make_pdf(["beta"]))
    real = pipeline.extract_pages

    def flaky(path, name):
        if name == "a.pdf":
            raise RuntimeError("boom")
        return real(path, name)

    monkeypatch.setattr(pipeline, "extract_pages", flaky)
    report = pipeline.rebuild_index()
    assert report.indexed == {"b.pdf": 1} and "RuntimeError: boom" in report.failed["a.pdf"]


def test_rebuild_with_missing_uploads_folder_clears_the_index(isolated_uploads_dir):
    pipeline.ingest_pages("gone.pdf", pages("gone.pdf"))
    report = pipeline.rebuild_index()
    assert report.indexed == {} and services.get_store().count() == 0
