"""Upload indexing, GET /documents and DELETE /documents/{file_name} (Stage 3E)."""

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import documents
from backend.config import settings
from backend.main import app
from backend.retrieval import services, vector_store
from tests.mocks.fake_embedder import FakeEmbedder

from tests.api.test_documents_api import _upload_from_threads, files_in, upload


def chunk_counts():
    return vector_store.read_file_chunk_counts(Path(settings.chroma_dir), settings.chroma_collection_name)


# ---- upload indexes the document ------------------------------------------


def test_upload_indexes_chunks_and_reports_counts(client, make_pdf):
    body = upload(client, ("hr.pdf", make_pdf(["Annual leave is 20 days.", "Sick leave is 10 days."]))).json()
    result = body["results"][0]
    assert result["success"] and result["chunk_count"] == 2
    assert result["max_chunk_tokens"] == FakeEmbedder().count_tokens("Annual leave is 20 days.")
    assert result["over_limit_chunks"] is None
    assert chunk_counts() == {"hr.pdf": 2}


def test_unicode_file_name_is_indexed_with_its_own_name(client, make_pdf):
    upload(client, ("हिन्दी café.pdf", make_pdf(["some text here"])))
    assert chunk_counts() == {"हिन्दी café.pdf": 1}
    assert services.get_store().verify_index({"हिन्दी café.pdf"}) == []


def test_over_limit_chunk_rejects_the_file_with_a_clear_report(client, make_pdf, isolated_uploads_dir, monkeypatch):
    fake = FakeEmbedder(max_tokens=5)
    services.set_embedder_override(fake)
    response = upload(client, ("long.pdf", make_pdf(["one two three four five six seven eight"])))
    result = response.json()["results"][0]
    assert response.status_code == 422 and not result["success"]
    assert result["over_limit_chunks"] == [{"chunk_id": "long.pdf:1:0", "token_count": 10}]
    assert result["max_chunk_tokens"] == 10 and "token" in result["error"]
    assert fake.document_calls == []
    assert files_in(isolated_uploads_dir) == [] and chunk_counts() == {}


def test_embedding_failure_gives_500_and_stores_nothing(client, make_pdf, isolated_uploads_dir, monkeypatch):
    monkeypatch.setattr(FakeEmbedder, "_encode", lambda self, texts, *, is_query: 1 / 0)
    response = upload(client, ("a.pdf", make_pdf(["text"])))
    assert response.status_code == 500
    assert files_in(isolated_uploads_dir) == [] and chunk_counts() == {}


def test_store_failure_gives_500_and_leaves_no_file_or_chunks(client, make_pdf, isolated_uploads_dir, monkeypatch):
    store = services.get_store()
    real = store.upsert_chunks

    def write_then_fail(**kwargs):
        real(**kwargs)
        raise RuntimeError("chroma died")

    monkeypatch.setattr(store, "upsert_chunks", lambda **kw: write_then_fail(**kw))
    response = upload(client, ("a.pdf", make_pdf(["text"])))
    assert response.status_code == 500
    assert files_in(isolated_uploads_dir) == [] and chunk_counts() == {}


def test_rename_failure_after_indexing_removes_the_chunks(client, make_pdf, isolated_uploads_dir, monkeypatch):
    def broken_replace(src, dst):
        assert chunk_counts() == {"a.pdf": 1}  # indexed before the rename
        raise OSError("disk error")

    monkeypatch.setattr(documents.os, "replace", broken_replace)
    response = upload(client, ("a.pdf", make_pdf(["text"])))
    assert response.status_code == 500
    assert files_in(isolated_uploads_dir) == [] and chunk_counts() == {}


def test_failed_chunk_cleanup_after_rename_failure_is_logged(client, make_pdf, monkeypatch, caplog):
    monkeypatch.setattr(documents.os, "replace", lambda s, d: (_ for _ in ()).throw(OSError("x")))
    monkeypatch.setattr(vector_store, "delete_file_chunks", lambda *a: (_ for _ in ()).throw(RuntimeError("y")))
    assert upload(client, ("a.pdf", make_pdf(["text"]))).status_code == 500
    assert "rebuild_index" in caplog.text


def test_duplicate_upload_is_409_and_keeps_the_original_chunks(client, make_pdf):
    upload(client, ("a.pdf", make_pdf(["first version"])))
    before = services.get_store().query(services.get_embedder().embed_query("first version"), 5)
    assert upload(client, ("A.PDF", make_pdf(["totally different words"]))).status_code == 409
    after = services.get_store().query(services.get_embedder().embed_query("first version"), 5)
    assert [c.text for c in after] == [c.text for c in before] == ["first version"]


def test_one_failing_file_does_not_affect_the_others(client, make_pdf):
    body = upload(client, ("good.pdf", make_pdf(["fine"])), ("bad.pdf", b"%PDF-1.4 junk"), ("good2.pdf", make_pdf(["also fine"]))).json()
    assert [r["success"] for r in body["results"]] == [True, False, True]
    assert chunk_counts() == {"good.pdf": 1, "good2.pdf": 1}


def test_embedding_runs_outside_the_store_lock_and_storing_inside(client, make_pdf, monkeypatch):
    seen = {}
    real_encode = FakeEmbedder._encode

    def encode(self, texts, *, is_query):
        seen["embed_locked"] = documents._STORE_LOCK.locked()
        return real_encode(self, texts, is_query=is_query)

    monkeypatch.setattr(FakeEmbedder, "_encode", encode)
    real_store = documents.pipeline.store_document

    def store(prepared, store=None):
        seen["store_locked"] = documents._STORE_LOCK.locked()
        return real_store(prepared, store)

    monkeypatch.setattr(documents.pipeline, "store_document", store)
    upload(client, ("a.pdf", make_pdf(["text"])))
    assert seen == {"embed_locked": False, "store_locked": True}


def test_same_name_race_indexes_only_the_winner(make_pdf, isolated_uploads_dir):
    contents = [make_pdf([f"unique{i} words"]) for i in range(6)]
    outcomes = _upload_from_threads("race.pdf", contents, isolated_uploads_dir)
    assert sorted(s for s, _ in outcomes).count(200) == 1
    assert sorted(s for s, _ in outcomes).count(409) == 5
    assert chunk_counts() == {"race.pdf": 1}
    winner = next(c for s, c in outcomes if s == 200)
    assert (isolated_uploads_dir / "race.pdf").read_bytes() == winner


# ---- GET /documents ---------------------------------------------------------


def test_list_is_empty_when_nothing_exists(client):
    assert client.get("/documents").json() == {"documents": [], "orphan_files": []}


def test_list_shows_pdfs_with_status_and_ignores_other_files(client, make_pdf, isolated_uploads_dir):
    upload(client, ("b.pdf", make_pdf(["bee", "bee two"])))
    upload(client, ("a.pdf", make_pdf(["ay"])))
    (isolated_uploads_dir / "plain.pdf").write_bytes(make_pdf(["never indexed"]))
    (isolated_uploads_dir / ".upload-zz.part").write_bytes(b"partial")
    (isolated_uploads_dir / "notes.txt").write_text("x")
    (isolated_uploads_dir / "folder.pdf").mkdir()
    services.get_store().upsert_chunks(
        ids=["gone.pdf:1:0"], documents=["x"], embeddings=[FakeEmbedder().embed_query("x")],
        file_names=["gone.pdf"], page_numbers=[1], chunk_indices=[0],
    )

    body = client.get("/documents").json()

    assert [(d["file_name"], d["indexed"], d["chunk_count"]) for d in body["documents"]] == [
        ("a.pdf", True, 1), ("b.pdf", True, 2), ("plain.pdf", False, 0),
    ]
    assert all(d["size_bytes"] > 0 for d in body["documents"])
    assert body["orphan_files"] == ["gone.pdf"]


def test_listing_does_not_need_the_embedding_model(client, make_pdf, monkeypatch):
    upload(client, ("a.pdf", make_pdf(["text"])))

    def no_model():
        raise AssertionError("model must not be loaded to list documents")

    monkeypatch.setattr(services, "get_embedder", no_model)
    assert client.get("/documents").json()["documents"][0]["indexed"] is True


# ---- DELETE /documents/{file_name} -----------------------------------------


def test_delete_removes_the_pdf_and_only_its_chunks(client, make_pdf, isolated_uploads_dir):
    upload(client, ("a.pdf", make_pdf(["alpha", "alpha two"])))
    upload(client, ("b.pdf", make_pdf(["beta"])))
    response = client.delete("/documents/a.pdf")
    assert response.status_code == 200
    assert response.json() == {"file_name": "a.pdf", "chunks_removed": 2}
    assert files_in(isolated_uploads_dir) == ["b.pdf"] and chunk_counts() == {"b.pdf": 1}


def test_delete_then_upload_again_works(client, make_pdf):
    upload(client, ("a.pdf", make_pdf(["alpha"])))
    client.delete("/documents/a.pdf")
    assert upload(client, ("a.pdf", make_pdf(["new alpha"]))).status_code == 200
    assert chunk_counts() == {"a.pdf": 1}


def test_delete_matches_case_insensitively_and_uses_the_stored_name(client, make_pdf, isolated_uploads_dir):
    upload(client, ("Guide.pdf", make_pdf(["alpha"])))
    assert client.delete("/documents/GUIDE.PDF").json()["file_name"] == "Guide.pdf"
    assert files_in(isolated_uploads_dir) == []


def test_delete_with_a_unicode_name(client, make_pdf):
    upload(client, ("हिन्दी.pdf", make_pdf(["alpha"])))
    assert client.delete("/documents/हिन्दी.pdf").status_code == 200
    assert chunk_counts() == {}


@pytest.mark.parametrize(
    "path", ["missing.pdf", "..%2F..%2Fetc%2Fpasswd", "%2E%2E%2Fsecret.pdf", ".upload-zz.part", "notes.txt", "%20.%20"]
)
def test_delete_unknown_or_dangerous_names_give_404(client, make_pdf, isolated_uploads_dir, path):
    (isolated_uploads_dir.parent / "secret.pdf").write_bytes(make_pdf(["outside"]))
    isolated_uploads_dir.mkdir()
    (isolated_uploads_dir / ".upload-zz.part").write_bytes(b"x")
    (isolated_uploads_dir / "notes.txt").write_text("x")
    assert client.delete(f"/documents/{path}").status_code == 404
    assert (isolated_uploads_dir.parent / "secret.pdf").exists()
    assert sorted(files_in(isolated_uploads_dir)) == [".upload-zz.part", "notes.txt"]


def test_delete_removes_chunks_before_the_file(client, make_pdf, isolated_uploads_dir, monkeypatch):
    upload(client, ("a.pdf", make_pdf(["alpha"])))
    order = []
    real_delete = vector_store.delete_file_chunks

    def delete_chunks(*args):
        order.append(("chunks", (isolated_uploads_dir / "a.pdf").exists()))
        return real_delete(*args)

    monkeypatch.setattr(vector_store, "delete_file_chunks", delete_chunks)
    client.delete("/documents/a.pdf")
    assert order == [("chunks", True)]  # the PDF still existed when the chunks were removed


def test_failed_file_delete_leaves_a_not_indexed_pdf_not_orphan_chunks(make_pdf, isolated_uploads_dir, monkeypatch):
    client = TestClient(app, raise_server_exceptions=False)
    upload(client, ("a.pdf", make_pdf(["alpha"])))

    def broken_unlink(self, *a, **k):
        raise PermissionError("locked")

    with monkeypatch.context() as patch:  # scoped: undo() would also revert the autouse fixtures
        patch.setattr(Path, "unlink", broken_unlink)
        assert client.delete("/documents/a.pdf").status_code == 500

    body = client.get("/documents").json()
    assert body["orphan_files"] == []
    assert [(d["file_name"], d["indexed"]) for d in body["documents"]] == [("a.pdf", False)]


def test_delete_without_any_index_still_removes_the_pdf(client, make_pdf, isolated_uploads_dir):
    isolated_uploads_dir.mkdir()
    (isolated_uploads_dir / "plain.pdf").write_bytes(make_pdf(["never indexed"]))
    assert client.delete("/documents/plain.pdf").json()["chunks_removed"] == 0
    assert files_in(isolated_uploads_dir) == []


def test_delete_holds_the_store_lock(client, make_pdf, monkeypatch):
    upload(client, ("a.pdf", make_pdf(["alpha"])))
    seen = []
    real = vector_store.delete_file_chunks
    monkeypatch.setattr(vector_store, "delete_file_chunks", lambda *a: (seen.append(documents._STORE_LOCK.locked()), real(*a))[1])
    client.delete("/documents/a.pdf")
    assert seen == [True]


# ---- model-free helpers ------------------------------------------------------


def test_helpers_on_a_missing_index(tmp_path):
    assert vector_store.read_file_chunk_counts(tmp_path / "none", "document_chunks") == {}
    assert vector_store.delete_file_chunks(tmp_path / "none", "document_chunks", "x.pdf") == 0


def test_read_file_chunk_counts_pages_through_batches(client, make_pdf, monkeypatch):
    upload(client, ("a.pdf", make_pdf([f"page {i}" for i in range(7)])))
    monkeypatch.setattr(vector_store, "_MAX_SAFE_BATCH", 3)
    assert chunk_counts() == {"a.pdf": 7}
