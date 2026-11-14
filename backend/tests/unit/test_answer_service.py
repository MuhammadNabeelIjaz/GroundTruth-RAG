"""Tests for answer generation service (Stage 5)."""

from unittest.mock import MagicMock, patch

import pytest

from backend.conversation.store import (
    ConversationNotFoundError,
    SQLiteConversationStore,
)
from backend.generation.answer_service import answer_question
from tests.mocks.fake_llm import FakeLLMClient
from backend.ingestion import pipeline
from backend.ingestion.pdf_loader import PageText


def _populate():
    pages = [
        PageText("policy.pdf", 1, "Employees receive 25 days of annual paid leave each year."),
        PageText("policy.pdf", 2, "Sick leave is allocated at 10 days annually with full medical pay."),
        PageText("specs_a.pdf", 1, "Model A drone battery flight duration is 48 hours."),
        PageText("specs_b.pdf", 1, "Model B drone battery flight duration is 24 hours."),
    ]
    pipeline.ingest_pages("policy.pdf", pages[:2])
    pipeline.ingest_pages("specs_a.pdf", [pages[2]])
    pipeline.ingest_pages("specs_b.pdf", [pages[3]])


def test_answer_empty_question_raises():
    with pytest.raises(ValueError, match="Question must not be empty"):
        answer_question("")
    with pytest.raises(ValueError, match="Question must not be empty"):
        answer_question("   ")


def test_answer_no_retrieved_chunks_returns_refusal():
    # Empty store
    fake = FakeLLMClient()
    result = answer_question("What is the refund policy?", llm_client=fake)
    assert result.found is False
    assert "do not contain sufficient information" in result.answer
    assert result.retrieved_chunks == []
    # LLM should not even be called
    assert len(fake.call_history) == 0


def test_answer_grounded_success():
    _populate()
    fake = FakeLLMClient(default_answer="Employees are entitled to 25 days of annual paid leave.")
    result = answer_question("How much annual leave?", llm_client=fake)
    assert result.found is True
    assert result.answer == "Employees are entitled to 25 days of annual paid leave."
    assert len(result.retrieved_chunks) > 0
    assert result.retrieved_chunks[0].file_name == "policy.pdf"
    assert len(fake.call_history) == 1


def test_answer_insufficient_information_refusal_flagged():
    _populate()
    fake = FakeLLMClient(default_answer="The provided documents do not contain sufficient information to answer.")
    result = answer_question("What is the CEO's salary?", llm_client=fake)
    assert result.found is False
    assert "sufficient information" in result.answer.lower()


def test_answer_with_partial_caveat_and_citations_is_not_refusal():
    _populate()
    answer_with_caveat = (
        "Full-time employees are entitled to 25 days [Passage 1]. "
        "The provided documents do not contain sufficient information regarding part-time employees."
    )
    fake = FakeLLMClient(default_answer=answer_with_caveat)
    result = answer_question("How much leave?", llm_client=fake)
    assert result.found is True
    assert len(result.citations) > 0


def test_answer_conflicting_information_handling():
    _populate()
    conflict_answer = "Document specs_a.pdf states 48 hours, whereas specs_b.pdf states 24 hours."
    fake = FakeLLMClient(default_answer=conflict_answer)
    result = answer_question("What is the battery flight duration?", llm_client=fake)
    assert result.found is True
    assert "48 hours" in result.answer
    assert "24 hours" in result.answer
    assert len(result.retrieved_chunks) >= 2


def test_conversational_turn_nonexistent_id_raises(tmp_path):
    store = SQLiteConversationStore(tmp_path / "conv.db")
    with pytest.raises(ConversationNotFoundError):
        answer_question("Hello", conversation_id="missing-id", conversation_store=store)


def test_conversational_first_question_stores_messages(tmp_path):
    _populate()
    store = SQLiteConversationStore(tmp_path / "conv.db")
    conv = store.create_conversation("Drone Q&A")

    fake = FakeLLMClient(default_answer="Model A drone battery flight duration is 48 hours [Passage 1].")
    result = answer_question(
        "What is Model A?",
        conversation_id=conv.id,
        conversation_store=store,
        llm_client=fake,
    )
    assert result.found is True
    assert result.conversation_id == conv.id
    assert result.standalone_query == "What is Model A?"

    messages = store.get_messages(conv.id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "What is Model A?"
    assert messages[1].role == "assistant"
    assert "48 hours" in messages[1].content


def test_conversational_follow_up_question_rewriting(tmp_path):
    _populate()
    store = SQLiteConversationStore(tmp_path / "conv.db")
    conv = store.create_conversation("Drone Q&A")

    # Turn 1
    fake1 = FakeLLMClient(default_answer="Model A drone flight duration is 48 hours [Passage 1].")
    answer_question(
        "Tell me about Model A",
        conversation_id=conv.id,
        conversation_store=store,
        llm_client=fake1,
    )

    # Turn 2: Follow up with "What is its flight duration?"
    # Handler handles query rewrite vs answer generation
    def llm_handler(messages):
        sys = messages[0]["content"]
        if "reformulation" in sys:
            return "What is the flight duration of Model A drone?"
        return "The flight duration of Model A drone is 48 hours [Passage 1]."

    fake2 = FakeLLMClient(handler=llm_handler)
    result = answer_question(
        "What is its flight duration?",
        conversation_id=conv.id,
        conversation_store=store,
        llm_client=fake2,
    )
    assert result.found is True
    assert result.question == "What is its flight duration?"
    assert result.standalone_query == "What is the flight duration of Model A drone?"
    assert len(result.citations) > 0

    messages = store.get_messages(conv.id)
    assert len(messages) == 4
    assert messages[2].role == "user"
    assert messages[2].content == "What is its flight duration?"
    assert messages[2].standalone_query == "What is the flight duration of Model A drone?"
    assert messages[3].role == "assistant"


def test_conversational_empty_retrieval_refusal_stores_messages(tmp_path):
    store = SQLiteConversationStore(tmp_path / "conv.db")
    conv = store.create_conversation()

    fake = FakeLLMClient()
    result = answer_question(
        "What is the cafeteria lunch menu?",
        conversation_id=conv.id,
        conversation_store=store,
        llm_client=fake,
    )
    assert result.found is False
    assert result.citations == []

    messages = store.get_messages(conv.id)
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[1].found is False
    assert messages[1].sources == []


def test_answer_question_uses_default_groq_client_when_none_provided():
    _populate()
    with patch("backend.generation.answer_service.GroqClient") as mock_groq_cls:
        mock_instance = MagicMock()
        mock_instance.generate.return_value = "Employees receive 25 days leave [Passage 1]."
        mock_groq_cls.return_value = mock_instance

        result = answer_question("How much annual leave?", llm_client=None)
        assert result.found is True
        mock_instance.generate.assert_called_once()


def test_is_refusal_answer_matrix():
    from backend.generation.answer_service import is_refusal_answer
    from backend.retrieval.vector_store import RetrievedChunk

    chunks = [
        RetrievedChunk("c1", "Warranty is 24 months for normal indoor use.", "f.pdf", 1, 0, 0.85),
        RetrievedChunk("c2", "Power supply is rated at 30 W with USB-PD.", "f.pdf", 2, 1, 0.75),
        RetrievedChunk("c3", "Battery settings and operating parameters.", "f.pdf", 3, 2, 0.65),
    ]

    # TC-1: Direct refusal, no citations -> True
    assert is_refusal_answer("The provided documents do not contain sufficient information to answer this question.", chunks) is True

    # TC-2: Framed refusal, no citations -> True
    assert is_refusal_answer("Based on the provided documents, there is insufficient information to answer.", chunks) is True

    # TC-3: Refusal followed by passage mention -> True
    assert is_refusal_answer("The provided documents do not contain sufficient information to answer this question. While [Passage 3] mentions battery settings, operating hours are not stated.", chunks) is True

    # TC-4: Citation as subject of refusal predicate -> True
    assert is_refusal_answer("[Passage 1] does not contain sufficient information to determine the salary.", chunks) is True

    # TC-5: Transition word after passage mention -> True
    assert is_refusal_answer("While [Passage 1] discusses dimensions, the provided documents do not contain sufficient information about battery life.", chunks) is True

    # TC-6: Factual claim then caveat (Separate sentences) -> False (grounded answer)
    assert is_refusal_answer("The standard warranty period is 24 months [Passage 1]. The documents do not contain sufficient information regarding accidental damage.", chunks) is False

    # TC-7: Factual claim and caveat in SAME sentence -> False (grounded answer)
    assert is_refusal_answer("Full-time employees receive 25 days of annual leave [Passage 1], but the documents do not contain sufficient information regarding part-time employees.", chunks) is False

    # TC-8: Factual claim with semicolon caveat -> False (grounded answer)
    assert is_refusal_answer("The standard warranty is 24 months [Passage 1]; however, the documents do not mention accidental coverage.", chunks) is False

    # TC-9: Normal grounded response -> False
    assert is_refusal_answer("Employees receive 25 days of annual leave per year [Passage 1].", chunks) is False

    # TC-10: Framed grounded response -> False
    assert is_refusal_answer("Based on the provided documents, the power supply is rated at 30 W [Passage 2].", chunks) is False


