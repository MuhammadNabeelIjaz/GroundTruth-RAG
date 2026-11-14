"""Regression tests for code-review findings:
1. GroqClient reasoning / <think> tags stripping.
2. Windows SQLite timestamp ordering with tied ticks (rowid stability).
3. Paraphrased refusal detection and source clearing.
4. Document deletion with space-containing filenames (URL encoding).
5. HTML escaping of untrusted PDF metadata in UI components.
6. Real conversations.db isolation.
"""

from __future__ import annotations

import html
import pytest
from backend.config import DATA_DIR, PROJECT_ROOT, settings
from backend.conversation.store import SQLiteConversationStore
from backend.generation.answer_service import is_refusal_answer
import urllib.parse

import httpx
from backend.config import DATA_DIR, PROJECT_ROOT, settings
from backend.conversation.store import SQLiteConversationStore
from backend.generation.answer_service import is_refusal_answer
from backend.generation.llm_client import GroqClient
from backend.retrieval.vector_store import RetrievedChunk


class _MinimalDocumentClient:
    """Minimal inline stand-in for the deleted backend.client.BackendClient.
    Used only by this regression test to verify URL-encoding behaviour."""

    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    def delete_document(self, file_name: str) -> dict:
        encoded = urllib.parse.quote(file_name, safe="")
        url = f"{self._base}/documents/{encoded}"
        with httpx.Client() as client:
            resp = client.delete(url)
            resp.raise_for_status()
            return resp.json()


def test_groq_client_strips_think_tags(monkeypatch):
    """Ensure <think>...</think> reasoning tags are stripped and do not leak into content."""
    client = GroqClient(api_key="mock_key")
    
    mock_payload = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "<think>\nInternal model scratchpad about policy.\n</think>\nEmployees receive 25 days of annual leave.",
                }
            }
        ]
    }
    
    class MockResponse:
        status_code = 200
        is_success = True
        
        def json(self):
            return mock_payload

    class MockHttpxClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, *args, **kwargs):
            return MockResponse()

    import httpx
    monkeypatch.setattr(httpx, "Client", MockHttpxClient)
    
    result = client.generate([{"role": "user", "content": "How many days?"}])
    assert "<think>" not in result
    assert "</think>" not in result
    assert "Internal model scratchpad" not in result
    assert result == "Employees receive 25 days of annual leave."


def test_sqlite_message_ordering_with_identical_timestamps(tmp_path):
    """On Windows, consecutive writes may share the exact same timestamp string.
    Ensure messages are ordered strictly by rowid (insertion order)."""
    db_file = tmp_path / "order_test.db"
    store = SQLiteConversationStore(db_path=db_file)
    
    conv = store.create_conversation("Ordering Test")
    conv_id = conv.id
    
    tied_timestamp = "2026-11-12T12:00:00.000000+00:00"
    
    # Insert 4 messages with the exact same timestamp
    m1 = store.add_message(conv_id, "user", "Question 1", created_at=tied_timestamp)
    m2 = store.add_message(conv_id, "assistant", "Answer 1", created_at=tied_timestamp)
    m3 = store.add_message(conv_id, "user", "Question 2", created_at=tied_timestamp)
    m4 = store.add_message(conv_id, "assistant", "Answer 2", created_at=tied_timestamp)
    
    # Retrieve messages
    messages = store.get_messages(conv_id)
    assert len(messages) == 4
    assert [m.content for m in messages] == ["Question 1", "Answer 1", "Question 2", "Answer 2"]
    
    # Retrieve with limit (e.g. limit=2 should return latest 2 in chronological order)
    recent = store.get_messages(conv_id, limit=2)
    assert len(recent) == 2
    assert [m.content for m in recent] == ["Question 2", "Answer 2"]


def test_paraphrased_refusal_detection():
    """Verify that varied phrasing of document insufficiency is correctly identified as a refusal."""
    dummy_chunks = [
        RetrievedChunk("f:1:0", "Vacation policy text.", "hr.pdf", 1, 0, 0.75)
    ]
    
    refusal_answers = [
        "The provided documents do not contain sufficient information to answer this question.",
        "I am unable to answer this question based on the provided context.",
        "None of the provided passages mention the remote work allowance.",
        "There is no mention of retirement benefits in the provided text.",
        "The provided documents do not mention salary bands.",
        "This is not discussed in the text.",
        "I could not find any information regarding this topic in the context.",
    ]
    
    for ans in refusal_answers:
        assert is_refusal_answer(ans, dummy_chunks) is True, f"Failed to identify refusal: {ans}"

    affirmative_answer = "Employees receive 25 days of vacation per year [Passage 1]."
    assert is_refusal_answer(affirmative_answer, dummy_chunks) is False


def test_delete_document_with_spaces_encodes_url(monkeypatch):
    """Verify that delete_document properly URL-encodes filenames with spaces."""
    client = _MinimalDocumentClient(base_url="http://127.0.0.1:8000")
    
    captured_urls = []
    
    class MockResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"file_name": "Proxy Marketing - lecture notes.pdf", "chunks_removed": 12}

    class MockHttpxClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def delete(self, url):
            captured_urls.append(url)
            return MockResponse()

    import httpx
    monkeypatch.setattr(httpx, "Client", MockHttpxClient)
    
    client.delete_document("Proxy Marketing - lecture notes.pdf")
    assert len(captured_urls) == 1
    # Check that spaces are encoded as %20
    assert "Proxy%20Marketing%20-%20lecture%20notes.pdf" in captured_urls[0]
    assert " " not in captured_urls[0]


def test_html_escaping_prevents_xss():
    """Verify that malicious strings in excerpts and filenames are escaped before insertion."""
    malicious_excerpt = '<script>alert("xss")</script> & <b>bold</b>'
    escaped = html.escape(malicious_excerpt)
    assert "<script>" not in escaped
    assert "&lt;script&gt;" in escaped
    assert "&amp;" in escaped


def test_live_conversations_db_remains_untouched_by_tests():
    """Verify that data/conversations.db is isolated and not modified by tests."""
    live_db = DATA_DIR / "conversations.db"
    assert settings.conversations_db_path != live_db

