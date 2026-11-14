"""Tests for prompt formatting and message construction (Stage 5)."""

import pytest

from backend.generation.prompts import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    build_messages,
    format_context,
)
from backend.retrieval.vector_store import RetrievedChunk


def test_format_context_empty():
    assert format_context([]) == "No document passages were found."


def test_format_context_multiple_chunks():
    chunks = [
        RetrievedChunk("doc.pdf:1:0", "Annual leave is 25 days.", "doc.pdf", 1, 0, 0.85),
        RetrievedChunk("doc.pdf:2:0", "Sick leave is 10 days.", "doc.pdf", 2, 0, 0.72),
    ]
    formatted = format_context(chunks)
    assert "[Passage 1] (Source: doc.pdf, Page 1)" in formatted
    assert "Annual leave is 25 days." in formatted
    assert "[Passage 2] (Source: doc.pdf, Page 2)" in formatted
    assert "Sick leave is 10 days." in formatted


def test_build_messages_structure():
    chunks = [
        RetrievedChunk("spec.pdf:1:0", "Battery life is 48 hours.", "spec.pdf", 1, 0, 0.9),
    ]
    messages = build_messages("How long is battery life?", chunks)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "ONLY USE SUPPLIED FACTS" in messages[0]["content"]
    assert "UNTRUSTED CONTENT" in messages[0]["content"]

    assert messages[1]["role"] == "user"
    assert "Battery life is 48 hours." in messages[1]["content"]
    assert "Question: How long is battery life?" in messages[1]["content"]
