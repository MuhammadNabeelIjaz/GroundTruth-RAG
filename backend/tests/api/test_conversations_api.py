"""Tests for /conversations API endpoints (Stage 7)."""

import pytest
from fastapi.testclient import TestClient

from backend.conversation import store as conv_store_module
from backend.conversation.store import SQLiteConversationStore, set_conversation_store
from backend.generation import answer_service
from tests.mocks.fake_llm import FakeLLMClient
from backend.generation.llm_client import (
    LLMAuthError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from backend.retrieval.retriever import QueryTooLong


@pytest.fixture(autouse=True)
def isolated_conv_store(tmp_path):
    """Use an isolated SQLite DB for each test."""
    db_file = tmp_path / "api_test_conversations.db"
    store = SQLiteConversationStore(db_file)
    set_conversation_store(store)
    yield store
    store.close()
    set_conversation_store(None)


def _upload_sample(client, make_pdf):
    content = make_pdf([
        "Model A-100 drone has a 48-hour flight battery life and max payload 5kg.",
        "Model B-200 drone has a 24-hour flight battery life and max payload 10kg.",
    ])
    res = client.post(
        "/documents",
        files=[("files", ("drone_specs.pdf", content, "application/pdf"))],
    )
    assert res.status_code == 200


def test_create_conversation_endpoint(client):
    # With title
    res1 = client.post("/conversations", json={"title": "Drone Inquiries"})
    assert res1.status_code == 201
    data1 = res1.json()
    assert data1["title"] == "Drone Inquiries"
    assert data1["conversation_id"] is not None
    assert data1["message_count"] == 0

    # Without title
    res2 = client.post("/conversations", json={})
    assert res2.status_code == 201
    assert res2.json()["title"] == "New Conversation"

    # None body
    res3 = client.post("/conversations")
    assert res3.status_code == 201
    assert res3.json()["title"] == "New Conversation"


def test_list_conversations_endpoint(client):
    res_empty = client.get("/conversations")
    assert res_empty.status_code == 200
    assert res_empty.json()["total"] == 0
    assert res_empty.json()["conversations"] == []

    c1 = client.post("/conversations", json={"title": "Conv 1"}).json()
    c2 = client.post("/conversations", json={"title": "Conv 2"}).json()

    res = client.get("/conversations?limit=10&offset=0")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["conversations"]) == 2


def test_get_conversation_history_endpoint(client):
    # Non-existent
    res_404 = client.get("/conversations/non-existent-id")
    assert res_404.status_code == 404
    assert "not found" in res_404.json()["detail"].lower()

    # Empty conversation
    c = client.post("/conversations", json={"title": "Empty Conv"}).json()
    res = client.get(f"/conversations/{c['conversation_id']}")
    assert res.status_code == 200
    data = res.json()
    assert data["conversation_id"] == c["conversation_id"]
    assert data["title"] == "Empty Conv"
    assert data["messages"] == []


def test_delete_conversation_endpoint(client):
    # Non-existent
    res_404 = client.delete("/conversations/non-existent-id")
    assert res_404.status_code == 404

    # Existing
    c = client.post("/conversations", json={"title": "To Delete"}).json()
    res = client.delete(f"/conversations/{c['conversation_id']}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True

    # Confirm gone
    assert client.get(f"/conversations/{c['conversation_id']}").status_code == 404


def test_send_conversation_message_flow(client, make_pdf, monkeypatch):
    _upload_sample(client, make_pdf)
    conv = client.post("/conversations", json={"title": "Flight Inquiries"}).json()
    conv_id = conv["conversation_id"]

    # Turn 1: Initial Question
    fake_llm = FakeLLMClient(default_answer="Model A-100 has a 48-hour battery life [Passage 1].")
    monkeypatch.setattr(answer_service, "GroqClient", lambda: fake_llm)

    res1 = client.post(
        f"/conversations/{conv_id}/messages",
        json={"question": "What is Model A-100?"},
    )
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["conversation_id"] == conv_id
    assert data1["question"] == "What is Model A-100?"
    assert data1["standalone_query"] == "What is Model A-100?"
    assert data1["found"] is True
    assert "48-hour" in data1["answer"]
    assert len(data1["sources"]) > 0
    assert data1["sources"][0]["file_name"] == "drone_specs.pdf"

    # Turn 2: Follow-up question with pronoun "its"
    def multi_turn_handler(messages):
        sys_prompt = messages[0]["content"]
        if "reformulation" in sys_prompt:
            return "What is the flight battery life of Model A-100 drone?"
        return "The flight battery life of Model A-100 is 48 hours [Passage 1]."

    fake_llm2 = FakeLLMClient(handler=multi_turn_handler)
    monkeypatch.setattr(answer_service, "GroqClient", lambda: fake_llm2)

    res2 = client.post(
        f"/conversations/{conv_id}/messages",
        json={"question": "What is its battery life?"},
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["question"] == "What is its battery life?"
    assert data2["standalone_query"] == "What is the flight battery life of Model A-100 drone?"
    assert data2["found"] is True
    assert len(data2["sources"]) > 0

    # Verify conversation history has both turns (4 messages)
    history_res = client.get(f"/conversations/{conv_id}")
    assert history_res.status_code == 200
    hist = history_res.json()
    assert len(hist["messages"]) == 4
    assert hist["messages"][0]["role"] == "user"
    assert hist["messages"][0]["content"] == "What is Model A-100?"
    assert hist["messages"][1]["role"] == "assistant"
    assert hist["messages"][2]["role"] == "user"
    assert hist["messages"][2]["content"] == "What is its battery life?"
    assert hist["messages"][2]["standalone_query"] == "What is the flight battery life of Model A-100 drone?"
    assert hist["messages"][3]["role"] == "assistant"


def test_conversation_isolation(client, make_pdf, monkeypatch):
    """Ensure two conversations do not mix contexts."""
    _upload_sample(client, make_pdf)
    conv1 = client.post("/conversations", json={"title": "Conv A"}).json()
    conv2 = client.post("/conversations", json={"title": "Conv B"}).json()

    # Message in Conv A
    fake_a = FakeLLMClient(default_answer="Model A-100 details [Passage 1].")
    monkeypatch.setattr(answer_service, "GroqClient", lambda: fake_a)
    client.post(f"/conversations/{conv1['conversation_id']}/messages", json={"question": "Model A"})

    # Message in Conv B
    fake_b = FakeLLMClient(default_answer="Model B-200 details [Passage 1].")
    monkeypatch.setattr(answer_service, "GroqClient", lambda: fake_b)
    client.post(f"/conversations/{conv2['conversation_id']}/messages", json={"question": "Model B"})

    h1 = client.get(f"/conversations/{conv1['conversation_id']}").json()
    h2 = client.get(f"/conversations/{conv2['conversation_id']}").json()

    assert len(h1["messages"]) == 2
    assert "Model A" in h1["messages"][0]["content"]

    assert len(h2["messages"]) == 2
    assert "Model B" in h2["messages"][0]["content"]


def test_send_message_validation_errors(client):
    conv = client.post("/conversations").json()
    cid = conv["conversation_id"]

    # Empty question
    res_empty = client.post(f"/conversations/{cid}/messages", json={"question": ""})
    assert res_empty.status_code == 400

    # Invalid top_k
    res_k = client.post(f"/conversations/{cid}/messages", json={"question": "hi", "top_k": 0})
    assert res_k.status_code == 422

    # Invalid min_similarity
    res_sim = client.post(f"/conversations/{cid}/messages", json={"question": "hi", "min_similarity": 2.0})
    assert res_sim.status_code == 422

    # Non-existent conversation
    res_404 = client.post("/conversations/bad-id/messages", json={"question": "hi"})
    assert res_404.status_code == 404


def test_send_message_exception_mappings(client, make_pdf, monkeypatch):
    _upload_sample(client, make_pdf)
    conv = client.post("/conversations").json()
    cid = conv["conversation_id"]

    # QueryTooLong -> 422
    def raise_too_long(*args, **kwargs):
        raise QueryTooLong(300, 256)

    monkeypatch.setattr("backend.api.conversations.answer_question", raise_too_long)
    res = client.post(f"/conversations/{cid}/messages", json={"question": "test"})
    assert res.status_code == 422

    # LLMAuthError -> 502
    def raise_auth(*args, **kwargs):
        raise LLMAuthError("Invalid API key")

    monkeypatch.setattr("backend.api.conversations.answer_question", raise_auth)
    res = client.post(f"/conversations/{cid}/messages", json={"question": "test"})
    assert res.status_code == 502

    # LLMRateLimitError -> 429
    def raise_rate(*args, **kwargs):
        raise LLMRateLimitError("Quota exceeded")

    monkeypatch.setattr("backend.api.conversations.answer_question", raise_rate)
    res = client.post(f"/conversations/{cid}/messages", json={"question": "test"})
    assert res.status_code == 429

    # LLMTimeoutError -> 504
    def raise_timeout(*args, **kwargs):
        raise LLMTimeoutError("Timed out")

    monkeypatch.setattr("backend.api.conversations.answer_question", raise_timeout)
    res = client.post(f"/conversations/{cid}/messages", json={"question": "test"})
    assert res.status_code == 504

    # LLMResponseError -> 502
    def raise_response(*args, **kwargs):
        raise LLMResponseError("Bad JSON")

    monkeypatch.setattr("backend.api.conversations.answer_question", raise_response)
    res = client.post(f"/conversations/{cid}/messages", json={"question": "test"})
    assert res.status_code == 502

