"""Tests for backend/api/search.py (Stage 4)."""

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.ingestion import pipeline
from backend.ingestion.pdf_loader import PageText
from backend.retrieval import services
from tests.mocks.fake_embedder import FakeEmbedder


def _populate(client, make_pdf):
    """Helper to upload a real PDF via the API and ensure chunks are indexed."""
    content = make_pdf([
        "The project deadline is December 15, 2026. All reports must be finalized.",
        "Team members can work remotely up to two days per week with manager approval.",
    ])
    res = client.post(
        "/documents",
        files=[("files", ("handbook.pdf", content, "application/pdf"))],
    )
    assert res.status_code == 200


def test_search_empty_index_returns_empty_results(client):
    res = client.post("/search", json={"query": "deadline"})
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "deadline"
    assert data["total_found"] == 0
    assert data["results"] == []


def test_search_finds_relevant_chunks_with_metadata_and_excerpt(client, make_pdf):
    _populate(client, make_pdf)

    res = client.post("/search", json={"query": "project deadline December"})
    assert res.status_code == 200
    data = res.json()
    assert data["query"] == "project deadline December"
    assert data["total_found"] >= 1
    top = data["results"][0]
    assert top["file_name"] == "handbook.pdf"
    assert top["page_number"] == 1
    assert top["chunk_index"] == 0
    assert "December 15, 2026" in top["text"]
    assert "deadline" in top["excerpt"].lower()
    assert isinstance(top["similarity"], float)
    assert top["chunk_id"] == "handbook.pdf:1:0"


def test_search_with_top_k(client, make_pdf):
    _populate(client, make_pdf)

    res = client.post("/search", json={"query": "work reports", "top_k": 1})
    assert res.status_code == 200
    data = res.json()
    assert len(data["results"]) == 1
    assert data["total_found"] == 1


def test_search_with_min_similarity(client, make_pdf):
    _populate(client, make_pdf)

    # Search with very high similarity threshold
    res = client.post(
        "/search", json={"query": "remote work", "min_similarity": 0.999}
    )
    assert res.status_code == 200
    data = res.json()
    # Any returned must satisfy min_similarity
    for r in data["results"]:
        assert r["similarity"] >= 0.999


def test_search_empty_query_returns_400(client):
    res = client.post("/search", json={"query": ""})
    assert res.status_code == 400
    assert "Query must not be empty" in res.json()["detail"]

    res = client.post("/search", json={"query": "   "})
    assert res.status_code == 400
    assert "Query must not be empty" in res.json()["detail"]


def test_search_invalid_top_k_returns_422(client):
    res = client.post("/search", json={"query": "hello", "top_k": 0})
    assert res.status_code == 422
    assert "top_k must be between 1 and 100" in res.json()["detail"]

    res = client.post("/search", json={"query": "hello", "top_k": 101})
    assert res.status_code == 422
    assert "top_k must be between 1 and 100" in res.json()["detail"]


def test_search_invalid_min_similarity_returns_422(client):
    res = client.post("/search", json={"query": "hello", "min_similarity": -1.5})
    assert res.status_code == 422
    assert "min_similarity must be between -1.0 and 1.0" in res.json()["detail"]

    res = client.post("/search", json={"query": "hello", "min_similarity": 1.5})
    assert res.status_code == 422
    assert "min_similarity must be between -1.0 and 1.0" in res.json()["detail"]


def test_search_query_too_long_returns_422(client):
    fake = FakeEmbedder(max_tokens=8)
    services.set_embedder_override(fake)
    long_query = "this query has more words than allowed by the fake token limit"
    res = client.post("/search", json={"query": long_query})
    assert res.status_code == 422
    assert "limit is 8" in res.json()["detail"]


def test_make_excerpt_collapses_whitespace_and_truncates():
    from backend.api.search import _make_excerpt

    short_text = "   hello   world   "
    assert _make_excerpt(short_text) == "hello world"

    long_text = "word " * 60  # 300 chars
    excerpt = _make_excerpt(long_text)
    assert len(excerpt) == 201  # 200 chars + 1 ellipsis char
    assert excerpt.endswith("\u2026")
