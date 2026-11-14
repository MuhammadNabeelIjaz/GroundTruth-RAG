"""Tests for backend/retrieval/retriever.py (Stage 4)."""

import pytest

from backend.config import settings
from backend.ingestion import pipeline
from backend.ingestion.pdf_loader import PageText
from backend.retrieval import services
from tests.mocks.fake_embedder import FakeEmbedder
from backend.retrieval.retriever import QueryTooLong, retrieve


def _populate_sample_chunks():
    """Helper to ingest test pages into isolated chroma."""
    pages = [
        PageText("policy.pdf", 1, "Employees receive 25 days of annual paid time off each calendar year."),
        PageText("policy.pdf", 2, "Sick leave is allocated at 10 days annually with full medical coverage."),
        PageText("specs.pdf", 1, "The drone battery lasts for up to 48 hours under normal conditions."),
        PageText("specs.pdf", 2, "Maximum operating ceiling is 5000 meters above sea level."),
    ]
    pipeline.ingest_pages("policy.pdf", pages[:2])
    pipeline.ingest_pages("specs.pdf", pages[2:])


def test_retrieve_finds_relevant_chunk_and_metadata():
    _populate_sample_chunks()
    results = retrieve("annual paid time off")
    assert len(results) > 0
    top = results[0]
    assert top.file_name == "policy.pdf"
    assert top.page_number == 1
    assert top.chunk_id == "policy.pdf:1:0"
    assert "paid time off" in top.text
    assert top.similarity > 0.0


def test_retrieve_respects_top_k():
    _populate_sample_chunks()
    results = retrieve("policy specs battery leave", top_k=2)
    assert len(results) == 2


def test_retrieve_defaults_to_configured_top_k_and_min_similarity(monkeypatch):
    _populate_sample_chunks()
    monkeypatch.setattr(settings, "retrieval_top_k", 1)
    monkeypatch.setattr(settings, "min_similarity", 0.0)
    results = retrieve("battery")
    assert len(results) == 1


def test_retrieve_filters_by_specific_file_names():
    _populate_sample_chunks()
    results = retrieve("paid leave and drone battery", file_names=["specs.pdf"])
    assert len(results) > 0
    assert all(r.file_name == "specs.pdf" for r in results)


def test_retrieve_filters_by_min_similarity():
    _populate_sample_chunks()
    # High threshold filters out less similar chunks
    results_all = retrieve("annual paid time off", min_similarity=-1.0)
    results_high = retrieve("annual paid time off", min_similarity=0.999)
    assert len(results_high) <= len(results_all)
    for r in results_high:
        assert r.similarity >= 0.999


def test_empty_query_raises_value_error():
    with pytest.raises(ValueError, match="Query must not be empty"):
        retrieve("")
    with pytest.raises(ValueError, match="Query must not be empty"):
        retrieve("   ")


def test_invalid_top_k_raises_value_error():
    with pytest.raises(ValueError, match="top_k must be >= 1"):
        retrieve("test", top_k=0)
    with pytest.raises(ValueError, match="top_k must be >= 1"):
        retrieve("test", top_k=-5)


def test_invalid_min_similarity_raises_value_error():
    with pytest.raises(ValueError, match="min_similarity must be in"):
        retrieve("test", min_similarity=-1.5)
    with pytest.raises(ValueError, match="min_similarity must be in"):
        retrieve("test", min_similarity=1.5)


def test_query_too_long_raises_query_too_long():
    fake = FakeEmbedder(max_tokens=10)
    services.set_embedder_override(fake)
    long_query = "word " * 15  # 15 words + 2 special tokens = 17 > 10
    with pytest.raises(QueryTooLong) as exc_info:
        retrieve(long_query)
    assert exc_info.value.token_count > 10
    assert exc_info.value.max_tokens == 10
    assert "limit is 10" in str(exc_info.value)


def test_empty_store_returns_empty_list():
    # Chroma is empty in this test
    results = retrieve("any question")
    assert results == []


def test_retrieve_with_explicit_embedder_and_store():
    fake = FakeEmbedder()
    store = services.get_store()
    results = retrieve("hello world", embedder=fake, store=store)
    assert results == []
    assert len(fake.query_calls) == 1
    assert fake.query_calls[0] == "hello world"
