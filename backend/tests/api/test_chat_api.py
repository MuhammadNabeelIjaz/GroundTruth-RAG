"""Tests for /answer and /chat API endpoints (Stage 5)."""

import pytest
from fastapi.testclient import TestClient

from backend.generation import answer_service
from tests.mocks.fake_llm import FakeLLMClient
from backend.generation.llm_client import (
    LLMAuthError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from backend.retrieval import services
from tests.mocks.fake_embedder import FakeEmbedder


def _upload_sample(client, make_pdf):
    content = make_pdf([
        "Annual vacation entitlement is 25 days per calendar year.",
        "Sick leave covers up to 10 paid days.",
    ])
    res = client.post("/documents", files=[("files", ("employee_guide.pdf", content, "application/pdf"))])
    assert res.status_code == 200


def test_answer_empty_index_returns_refusal(client, monkeypatch):
    # Empty store -> refusal with found=False and empty sources
    res = client.post("/answer", json={"question": "What is the policy?"})
    assert res.status_code == 200
    data = res.json()
    assert data["found"] is False
    assert "sufficient information" in data["answer"].lower()
    assert data["sources"] == []


def test_answer_successful_grounded_response(client, make_pdf, monkeypatch):
    _upload_sample(client, make_pdf)
    fake_llm = FakeLLMClient(default_answer="Employees get 25 days vacation.")
    monkeypatch.setattr(answer_service, "GroqClient", lambda: fake_llm)

    res = client.post("/answer", json={"question": "How many days vacation?"})
    assert res.status_code == 200
    data = res.json()
    assert data["found"] is True
    assert data["answer"] == "Employees get 25 days vacation."
    assert len(data["sources"]) > 0
    top_source = data["sources"][0]
    assert top_source["file_name"] == "employee_guide.pdf"
    assert top_source["page_number"] == 1
    assert "vacation entitlement" in top_source["excerpt"].lower()


def test_chat_endpoint_alias_works(client, make_pdf, monkeypatch):
    _upload_sample(client, make_pdf)
    fake_llm = FakeLLMClient(default_answer="Employees get 25 days vacation.")
    monkeypatch.setattr(answer_service, "GroqClient", lambda: fake_llm)

    res = client.post("/chat", json={"question": "How many days vacation?"})
    assert res.status_code == 200
    assert res.json()["found"] is True


def test_answer_empty_question_returns_400(client):
    res = client.post("/answer", json={"question": ""})
    assert res.status_code == 400
    assert "Question must not be empty" in res.json()["detail"]

    res = client.post("/answer", json={"question": "   "})
    assert res.status_code == 400


def test_answer_invalid_top_k_returns_422(client):
    res = client.post("/answer", json={"question": "vacation", "top_k": 0})
    assert res.status_code == 422
    assert "top_k must be between 1 and 100" in res.json()["detail"]

    res = client.post("/answer", json={"question": "vacation", "top_k": 105})
    assert res.status_code == 422


def test_answer_invalid_min_similarity_returns_422(client):
    res = client.post("/answer", json={"question": "vacation", "min_similarity": -1.5})
    assert res.status_code == 422
    assert "min_similarity must be between -1.0 and 1.0" in res.json()["detail"]


def test_answer_query_too_long_returns_422(client):
    fake_embedder = FakeEmbedder(max_tokens=8)
    services.set_embedder_override(fake_embedder)
    long_question = "word " * 15
    res = client.post("/answer", json={"question": long_question})
    assert res.status_code == 422
    assert "limit is 8" in res.json()["detail"]


def test_answer_llm_auth_error_returns_502(client, make_pdf, monkeypatch):
    _upload_sample(client, make_pdf)

    class AuthFailClient:
        def generate(self, *args, **kwargs):
            raise LLMAuthError("Invalid API key")

    monkeypatch.setattr(answer_service, "GroqClient", AuthFailClient)
    res = client.post("/answer", json={"question": "vacation"})
    assert res.status_code == 502
    assert "LLM authentication error" in res.json()["detail"]


def test_answer_llm_rate_limit_returns_429(client, make_pdf, monkeypatch):
    _upload_sample(client, make_pdf)

    class RateLimitClient:
        def generate(self, *args, **kwargs):
            raise LLMRateLimitError("Too many requests")

    monkeypatch.setattr(answer_service, "GroqClient", RateLimitClient)
    res = client.post("/answer", json={"question": "vacation"})
    assert res.status_code == 429
    assert "LLM rate limit reached" in res.json()["detail"]


def test_answer_llm_timeout_returns_504(client, make_pdf, monkeypatch):
    _upload_sample(client, make_pdf)

    class TimeoutClient:
        def generate(self, *args, **kwargs):
            raise LLMTimeoutError("Read timed out")

    monkeypatch.setattr(answer_service, "GroqClient", TimeoutClient)
    res = client.post("/answer", json={"question": "vacation"})
    assert res.status_code == 504
    assert "LLM provider timed out" in res.json()["detail"]


def test_answer_llm_response_error_returns_502(client, make_pdf, monkeypatch):
    _upload_sample(client, make_pdf)

    class BadResponseClient:
        def generate(self, *args, **kwargs):
            raise LLMResponseError("Malformed JSON")

    monkeypatch.setattr(answer_service, "GroqClient", BadResponseClient)
    res = client.post("/answer", json={"question": "vacation"})
    assert res.status_code == 502
    assert "invalid response" in res.json()["detail"]


def test_answer_with_invalid_conversation_id_returns_404(client):
    res = client.post("/answer", json={"question": "vacation", "conversation_id": "nonexistent"})
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


def test_answer_with_valid_conversation_id_returns_200(client, make_pdf, monkeypatch):
    _upload_sample(client, make_pdf)
    # Create conversation first
    conv_res = client.post("/conversations", json={"title": "Chat API Conv"})
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["conversation_id"]

    fake_llm = FakeLLMClient(default_answer="Employees get 25 days vacation.")
    monkeypatch.setattr(answer_service, "GroqClient", lambda: fake_llm)

    res = client.post("/answer", json={"question": "How many days?", "conversation_id": conv_id})
    assert res.status_code == 200
    data = res.json()
    assert data["conversation_id"] == conv_id
    assert data["standalone_query"] == "How many days?"

