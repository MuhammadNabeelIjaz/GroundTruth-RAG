"""Verification for sample PDFs vs user uploads separation and protection."""

from pathlib import Path
import pytest
from backend.config import settings
from backend.main import _seed_sample_documents


def test_seed_sample_documents_indexes_without_copying_to_uploads(client, make_pdf, tmp_path, monkeypatch):
    """Sample PDFs in sample_dir must be indexed directly without copying into uploads_dir."""
    uploads = tmp_path / "uploads"
    samples = tmp_path / "sample_pdfs" / "Low"
    samples.mkdir(parents=True)
    uploads.mkdir(parents=True)

    sample_file = samples / "sample_doc.pdf"
    sample_file.write_bytes(make_pdf(["Sample document content for seeding test."]))

    monkeypatch.setattr(settings, "uploads_dir", uploads)
    monkeypatch.setattr(settings, "sample_dir", tmp_path / "sample_pdfs")

    _seed_sample_documents()

    # Verify: file was NOT copied into uploads
    assert not (uploads / "sample_doc.pdf").exists(), "Sample PDF was copied to uploads!"

    # Verify: file is listed via GET /documents
    resp = client.get("/documents")
    assert resp.status_code == 200
    docs = resp.json()["documents"]
    assert any(d["file_name"] == "sample_doc.pdf" for d in docs)
    assert resp.json()["orphan_files"] == []


def test_delete_user_upload_does_not_affect_sample_pdfs(client, make_pdf, tmp_path, monkeypatch):
    """Deleting a user upload must remove its chunks and file, but never affect sample PDFs."""
    uploads = tmp_path / "uploads"
    samples = tmp_path / "sample_pdfs" / "Medium"
    samples.mkdir(parents=True)
    uploads.mkdir(parents=True)

    sample_file = samples / "handbook.pdf"
    sample_file.write_bytes(make_pdf(["Company handbook sample text."]))

    monkeypatch.setattr(settings, "uploads_dir", uploads)
    monkeypatch.setattr(settings, "sample_dir", tmp_path / "sample_pdfs")

    _seed_sample_documents()

    # User uploads a new document
    upload_resp = client.post(
        "/documents",
        files=[("files", ("user_manual.pdf", make_pdf(["User uploaded content."]), "application/pdf"))],
    )
    assert upload_resp.status_code == 200

    # User uploads file exists in uploads_dir
    assert (uploads / "user_manual.pdf").exists()
    assert sample_file.exists()

    # Delete the user-uploaded document
    del_resp = client.delete("/documents/user_manual.pdf")
    assert del_resp.status_code == 200

    # User upload removed from uploads_dir, sample PDF completely untouched
    assert not (uploads / "user_manual.pdf").exists()
    assert sample_file.exists()


def test_deleting_sample_pdf_is_forbidden(client, make_pdf, tmp_path, monkeypatch):
    """Directly attempting to delete a protected sample PDF must return 403."""
    uploads = tmp_path / "uploads"
    samples = tmp_path / "sample_pdfs"
    samples.mkdir(parents=True)
    uploads.mkdir(parents=True)

    sample_file = samples / "protected.pdf"
    sample_file.write_bytes(make_pdf(["Protected sample document."]))

    monkeypatch.setattr(settings, "uploads_dir", uploads)
    monkeypatch.setattr(settings, "sample_dir", samples)

    _seed_sample_documents()

    # Attempt delete
    resp = client.delete("/documents/protected.pdf")
    assert resp.status_code == 403
    assert "protected sample document and cannot be deleted" in resp.json()["detail"]
    assert sample_file.exists()
