"""LLM Client and exceptions for hosted LLM generation (Stage 5).

Supports the Groq API (OpenAI-compatible chat completions endpoint).
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LLMError(Exception):
    """Base exception for all LLM client failures."""


class LLMAuthError(LLMError):
    """API key is missing, invalid, or unauthorized (HTTP 401/403)."""


class LLMRateLimitError(LLMError):
    """Rate limit or quota exceeded (HTTP 429)."""


class LLMTimeoutError(LLMError):
    """Network request to the LLM provider timed out."""


class LLMConnectionError(LLMError):
    """Network connection failure or unreachable provider."""


class LLMResponseError(LLMError):
    """Provider returned a non-200 status code or malformed JSON payload."""


# ---------------------------------------------------------------------------
# Abstract LLM Client Interface
# ---------------------------------------------------------------------------


class LLMClient(ABC):
    """Abstract interface for LLM completion generation."""

    @abstractmethod
    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate completion text given chat messages."""


# ---------------------------------------------------------------------------
# Groq LLM Client Implementation
# ---------------------------------------------------------------------------


class GroqClient(LLMClient):
    """Groq API client using httpx.Client."""

    GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.groq_api_key
        self._model = model or settings.llm_model
        self._timeout = timeout if timeout is not None else settings.llm_timeout_seconds

    @property
    def model_name(self) -> str:
        return self._model

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Call Groq chat completions endpoint with error mapping."""
        if not self._api_key or not self._api_key.strip():
            raise LLMAuthError("GROQ_API_KEY is not set or is empty.")

        resolved_temp = temperature if temperature is not None else settings.llm_temperature
        resolved_max_tokens = max_tokens if max_tokens is not None else 500
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": resolved_temp,
            "max_tokens": resolved_max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        max_attempts = 3
        last_exc: Exception | None = None
        response: httpx.Response | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                request_timeout = httpx.Timeout(self._timeout, connect=15.0)
                with httpx.Client(timeout=request_timeout) as client:
                    response = client.post(
                        self.GROQ_API_URL,
                        json=payload,
                        headers=headers,
                    )
            except httpx.TimeoutException as exc:
                logger.warning("Groq API request timed out (attempt %d/%d): %s", attempt, max_attempts, exc)
                last_exc = LLMTimeoutError(f"Groq API timed out: {exc}")
                if attempt < max_attempts:
                    import time
                    time.sleep(1.5)
                    continue
                raise last_exc from exc
            except httpx.NetworkError as exc:
                logger.warning("Groq API network error (attempt %d/%d): %s", attempt, max_attempts, exc)
                last_exc = LLMConnectionError(f"Network error connecting to Groq API: {exc}")
                if attempt < max_attempts:
                    import time
                    time.sleep(1.5)
                    continue
                raise last_exc from exc
            except Exception as exc:
                logger.warning("Groq API connection/network error (attempt %d/%d): %s", attempt, max_attempts, exc)
                last_exc = LLMConnectionError(f"Connection failed to Groq API: {exc}")
                if attempt < max_attempts:
                    import time
                    time.sleep(1.5)
                    continue
                raise last_exc from exc

            if response.status_code == 429 and attempt < max_attempts:
                logger.warning("Groq rate limit (429) hit on attempt %d/%d. Waiting 2.5s before retry...", attempt, max_attempts)
                import time
                time.sleep(2.5)
                continue

            break

        if response is None:
            raise last_exc or LLMConnectionError("Failed to receive response from Groq API")

        if response.status_code in (401, 403):
            logger.error("Groq API authentication failed (status %d)", response.status_code)
            raise LLMAuthError(f"Groq authentication error ({response.status_code}): {response.text}")
        if response.status_code == 429:
            logger.warning("Groq API rate limit exceeded")
            raise LLMRateLimitError(f"Groq rate limit exceeded (429): {response.text}")
        if not response.is_success:
            logger.error("Groq API error HTTP %d: %s", response.status_code, response.text)
            raise LLMResponseError(f"Groq API error {response.status_code}: {response.text}")

        try:
            data = response.json()
            choice = data["choices"][0]["message"]
            content = choice.get("content")
            if content is None or not content.strip():
                # Some reasoning models put the text in 'reasoning' or return empty string
                content = choice.get("reasoning", "") or ""
            # Strip any internal chain-of-thought <think>...</think> tags if returned
            content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
            return content
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            logger.error("Failed to parse Groq response JSON: %s", exc)
            raise LLMResponseError(f"Malformed response payload from Groq: {exc}") from exc
