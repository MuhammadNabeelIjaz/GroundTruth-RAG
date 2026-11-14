"""Unit tests for query rewriter (Stage 7)."""

from unittest.mock import MagicMock, patch

import pytest

from backend.conversation.store import MessageRecord
from tests.mocks.fake_llm import FakeLLMClient
from backend.generation.rewriter import (
    clean_rewritten_query,
    format_history_for_rewriter,
    rewrite_query,
)


def _msg(role: str, content: str) -> MessageRecord:
    return MessageRecord(
        id="test-id",
        conversation_id="conv-1",
        role=role,
        content=content,
        standalone_query=None,
        found=True,
        sources=[],
        created_at="2026-11-12T00:00:00Z",
    )


def test_rewrite_empty_question():
    assert rewrite_query("", []) == ""
    assert rewrite_query("   ", []) == ""


def test_rewrite_with_empty_history():
    llm = FakeLLMClient(default_answer="Should not be called")
    result = rewrite_query("What is the leave policy?", [], llm_client=llm)
    assert result == "What is the leave policy?"
    assert len(llm.call_history) == 0


def test_rewrite_with_blank_history():
    llm = FakeLLMClient(default_answer="Should not be called")
    history = [_msg("user", "   "), _msg("assistant", "\n\n")]
    result = rewrite_query("What is the leave policy?", history, llm_client=llm)
    assert result == "What is the leave policy?"
    assert len(llm.call_history) == 0


def test_rewrite_follow_up_pronoun_resolution():
    history = [
        _msg("user", "What is Model A-100?"),
        _msg("assistant", "Model A-100 is a commercial drone with 48 hours battery life."),
    ]
    llm = FakeLLMClient(default_answer="What is the battery life of Model A-100?")

    result = rewrite_query("What is its battery life?", history, llm_client=llm)
    assert result == "What is the battery life of Model A-100?"
    assert len(llm.call_history) == 1
    messages = llm.call_history[0]["messages"]
    assert "What is its battery life?" in messages[1]["content"]
    assert "Model A-100" in messages[1]["content"]


def test_clean_rewritten_query():
    fallback = "Original question?"

    assert clean_rewritten_query("", fallback) == fallback
    assert clean_rewritten_query("   ", fallback) == fallback
    assert clean_rewritten_query('"What is Model A-100?"', fallback) == "What is Model A-100?"
    assert clean_rewritten_query("'What is Model A-100?'", fallback) == "What is Model A-100?"
    assert clean_rewritten_query("Standalone query: What is Model A?", fallback) == "What is Model A?"
    assert clean_rewritten_query("Rewritten query: What is Model A?", fallback) == "What is Model A?"
    assert clean_rewritten_query("Rewritten question: What is Model A?", fallback) == "What is Model A?"
    assert clean_rewritten_query("Query: What is Model A?", fallback) == "What is Model A?"
    # When prefix removal results in empty string
    assert clean_rewritten_query("Standalone query:", fallback) == fallback


def test_rewrite_query_fallback_on_empty_llm_response():
    history = [_msg("user", "Hello"), _msg("assistant", "Hi")]
    llm = FakeLLMClient(default_answer="   ")
    result = rewrite_query("What is its weight?", history, llm_client=llm)
    assert result == "What is its weight?"


def test_format_history_windowing():
    messages = [
        _msg("user", f"Question {i}") for i in range(10)
    ]
    formatted = format_history_for_rewriter(messages, max_turns=2)
    lines = formatted.splitlines()
    # 2 turns * 2 = 4 messages max
    assert len(lines) == 4
    assert "Question 6" in lines[0]
    assert "Question 9" in lines[3]

    assert format_history_for_rewriter([]) == ""
    # max_turns <= 0 includes all
    all_formatted = format_history_for_rewriter(messages, max_turns=0)
    assert len(all_formatted.splitlines()) == 10


def test_rewrite_uses_default_groq_client_when_none_provided():
    history = [_msg("user", "Hello"), _msg("assistant", "Hi")]
    with patch("backend.generation.rewriter.GroqClient") as mock_groq_cls:
        mock_instance = MagicMock()
        mock_instance.generate.return_value = "What is the flight time of Drone X?"
        mock_groq_cls.return_value = mock_instance

        result = rewrite_query("What is its flight time?", history, llm_client=None)
        assert result == "What is the flight time of Drone X?"
        mock_instance.generate.assert_called_once()

