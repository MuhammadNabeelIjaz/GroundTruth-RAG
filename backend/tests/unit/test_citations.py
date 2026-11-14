"""Tests for source citation validation and extraction (Stage 6)."""

import pytest

from backend.generation.citations import (
    compute_lexical_overlap,
    extract_best_excerpt,
    extract_cited_passage_indices,
    validate_citations,
)
from backend.retrieval.vector_store import RetrievedChunk


def _make_chunk(cid, text, file_name="policy.pdf", page=1, idx=0, sim=0.8):
    return RetrievedChunk(cid, text, file_name, page, idx, sim)


def test_extract_cited_passage_indices():
    assert extract_cited_passage_indices("According to [Passage 1] and [Passage 2].", 3) == {1, 2}
    assert extract_cited_passage_indices("See [Passage 5].", 3) == set()  # 5 > total 3
    assert extract_cited_passage_indices("As shown in [1, 2].", 3) == {1, 2}
    assert extract_cited_passage_indices("Passage 2 confirms this.", 3) == {2}
    assert extract_cited_passage_indices("No passages mentioned.", 3) == set()
    assert extract_cited_passage_indices("", 3) == set()
    assert extract_cited_passage_indices("Text", 0) == set()


def test_compute_lexical_overlap():
    assert compute_lexical_overlap("", "some text") == 0.0
    assert compute_lexical_overlap("some text", "") == 0.0
    assert compute_lexical_overlap("completely disjoint words", "unrelated vocabulary here") == 0.0
    overlap = compute_lexical_overlap("annual paid leave entitlement", "Employees receive annual paid leave")
    assert overlap > 0.5


def test_extract_best_excerpt():
    text = "Short text."
    assert extract_best_excerpt(text, "Short") == "Short text."

    long_text = (
        "Introduction to company rules. "
        "Employees are entitled to 25 days of annual paid leave every year. "
        "Other rules apply."
    )
    excerpt = extract_best_excerpt(long_text, "How many days of annual paid leave?")
    assert "25 days of annual paid leave" in excerpt

    # Test sentence splitting on punctuation where sentence is shorter than max_chars
    s1 = "This is a sentence. " + "Another sentence. " * 20
    res1 = extract_best_excerpt(s1, "This is a sentence.")
    assert res1 == "This is a sentence."

    # Test sentence longer than max_chars gets truncated with ellipsis
    long_single = "word " * 60
    res2 = extract_best_excerpt(long_single, "test")
    assert len(res2) <= 201
    assert res2.endswith("\u2026")


def test_compute_lexical_overlap_edge_cases():
    assert compute_lexical_overlap("a b c", "x y z") == 0.0
    assert compute_lexical_overlap("hello", "   ") == 0.0


def test_extract_cited_passage_indices_complex():
    text = "Refer to [bracket without number] and [1, 2, 3]."
    assert extract_cited_passage_indices(text, 5) == {1, 2, 3}



def test_validate_citations_refusal_returns_empty():
    chunks = [_make_chunk("c1", "text")]
    citations = validate_citations("The provided documents do not contain sufficient info.", chunks, is_refusal=True)
    assert citations == []


def test_validate_citations_explicit_passage_tags():
    chunks = [
        _make_chunk("c1", "Annual leave is 25 days.", page=1),
        _make_chunk("c2", "Sick leave is 10 days.", page=2),
        _make_chunk("c3", "Remote work is permitted.", page=3),
    ]
    # Answer only cites Passage 1 and 2
    answer = "Employees have 25 days annual leave [Passage 1] and 10 days sick leave [Passage 2]."
    citations = validate_citations(answer, chunks)
    assert len(citations) == 2
    assert [c.page_number for c in citations] == [1, 2]
    assert [c.chunk_id for c in citations] == ["c1", "c2"]


def test_validate_citations_implicit_lexical_overlap():
    chunks = [
        _make_chunk("c1", "Annual leave entitlement is 25 days per calendar year.", page=1),
        _make_chunk("c2", "Quadcopter flight altitude is 5000 meters above sea level.", page=2),
    ]
    # No [Passage X] tag, but mentions annual leave
    answer = "Employees receive 25 days of annual leave."
    citations = validate_citations(answer, chunks)
    assert len(citations) == 1
    assert citations[0].chunk_id == "c1"
    assert citations[0].page_number == 1


def test_validate_citations_fallback_strong_similarity():
    chunks = [
        _make_chunk("c1", "Employees receive 25 days of vacation annually.", page=1, sim=0.85),
    ]
    # Synonym used with low word overlap
    answer = "The annual time-off allocation is 25."
    citations = validate_citations(answer, chunks, min_overlap_threshold=0.99)
    assert len(citations) == 1
    assert citations[0].chunk_id == "c1"


def test_validate_citations_duplicate_chunk_deduplicated():
    chunks = [
        _make_chunk("c1", "Annual leave is 25 days.", page=1),
    ]
    answer = "[Passage 1] and also in [Passage 1]."
    citations = validate_citations(answer, chunks)
    assert len(citations) == 1
