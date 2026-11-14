"""Tests for LLM client and error handling (Stage 5)."""

import httpx
import pytest

from tests.mocks.fake_llm import FakeLLMClient
from backend.generation.llm_client import (
    GroqClient,
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)


def test_fake_llm_records_history_and_returns_default():
    fake = FakeLLMClient(default_answer="Grounded answer")
    messages = [{"role": "user", "content": "hi"}]
    answer = fake.generate(messages, temperature=0.5, max_tokens=100)
    assert answer == "Grounded answer"
    assert len(fake.call_history) == 1
    assert fake.call_history[0]["temperature"] == 0.5
    assert fake.call_history[0]["max_tokens"] == 100


def test_fake_llm_custom_handler():
    fake = FakeLLMClient(handler=lambda msgs: f"Echo: {msgs[-1]['content']}")
    assert fake.generate([{"role": "user", "content": "test"}]) == "Echo: test"


def test_fake_llm_responses_queue():
    fake = FakeLLMClient(default_answer="Fallback", responses=["First response", "Second response"])
    assert fake.generate([{"role": "user", "content": "1"}]) == "First response"
    assert fake.generate([{"role": "user", "content": "2"}]) == "Second response"
    assert fake.generate([{"role": "user", "content": "3"}]) == "Fallback"


def test_groq_missing_api_key_raises_auth_error():
    client = GroqClient(api_key="")
    with pytest.raises(LLMAuthError, match="GROQ_API_KEY is not set"):
        client.generate([{"role": "user", "content": "hello"}])


def test_groq_successful_response(monkeypatch):
    def mock_post(self, url, json, headers):
        class MockResponse:
            status_code = 200
            is_success = True

            def json(self):
                return {
                    "choices": [
                        {"message": {"role": "assistant", "content": "Mocked response"}}
                    ]
                }

        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    client = GroqClient(api_key="valid-key", model="test-model")
    assert client.model_name == "test-model"
    res = client.generate([{"role": "user", "content": "hello"}], max_tokens=150)
    assert res == "Mocked response"


def test_groq_reasoning_fallback(monkeypatch):
    def mock_post(self, url, json, headers):
        class MockResponse:
            status_code = 200
            is_success = True

            def json(self):
                return {
                    "choices": [
                        {"message": {"role": "assistant", "content": "", "reasoning": "Reasoning fallback"}}
                    ]
                }

        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    client = GroqClient(api_key="valid-key")
    res = client.generate([{"role": "user", "content": "hello"}])
    assert res == "Reasoning fallback"


def test_groq_timeout_maps_to_llm_timeout_error(monkeypatch):
    def mock_post(self, url, json, headers):
        raise httpx.TimeoutException("Read timed out")

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    client = GroqClient(api_key="valid-key")
    with pytest.raises(LLMTimeoutError, match="timed out"):
        client.generate([{"role": "user", "content": "hello"}])


def test_groq_network_error_maps_to_connection_error(monkeypatch):
    def mock_post(self, url, json, headers):
        raise httpx.NetworkError("DNS failure")

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    client = GroqClient(api_key="valid-key")
    with pytest.raises(LLMConnectionError, match="Network error"):
        client.generate([{"role": "user", "content": "hello"}])


def test_groq_generic_exception_maps_to_connection_error(monkeypatch):
    def mock_post(self, url, json, headers):
        raise RuntimeError("Unexpected socket error")

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    client = GroqClient(api_key="valid-key")
    with pytest.raises(LLMConnectionError, match="Connection failed"):
        client.generate([{"role": "user", "content": "hello"}])


def test_groq_auth_failure_401(monkeypatch):
    def mock_post(self, url, json, headers):
        class MockResponse:
            status_code = 401
            is_success = False
            text = "Invalid API Key"

        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    client = GroqClient(api_key="bad-key")
    with pytest.raises(LLMAuthError, match="authentication error"):
        client.generate([{"role": "user", "content": "hello"}])


def test_groq_rate_limit_429(monkeypatch):
    def mock_post(self, url, json, headers):
        class MockResponse:
            status_code = 429
            is_success = False
            text = "Rate limit exceeded"

        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    client = GroqClient(api_key="valid-key")
    with pytest.raises(LLMRateLimitError, match="rate limit exceeded"):
        client.generate([{"role": "user", "content": "hello"}])


def test_groq_server_error_500(monkeypatch):
    def mock_post(self, url, json, headers):
        class MockResponse:
            status_code = 500
            is_success = False
            text = "Internal Server Error"

        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    client = GroqClient(api_key="valid-key")
    with pytest.raises(LLMResponseError, match="Groq API error 500"):
        client.generate([{"role": "user", "content": "hello"}])


def test_groq_malformed_json_response(monkeypatch):
    def mock_post(self, url, json, headers):
        class MockResponse:
            status_code = 200
            is_success = True

            def json(self):
                return {"choices": []}  # Missing choice element

        return MockResponse()

    monkeypatch.setattr(httpx.Client, "post", mock_post)
    client = GroqClient(api_key="valid-key")
    with pytest.raises(LLMResponseError, match="Malformed response payload"):
        client.generate([{"role": "user", "content": "hello"}])
