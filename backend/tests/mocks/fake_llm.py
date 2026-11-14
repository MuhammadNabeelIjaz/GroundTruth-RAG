"""Deterministic Fake LLM client for testing.

Provides canned responses or customizable generation without calling Groq API.
"""

from __future__ import annotations

from typing import Any, Callable

from backend.generation.llm_client import LLMClient


class FakeLLMClient(LLMClient):
    """Fake LLM client that returns predefined answers or calls a handler."""

    def __init__(
        self,
        default_answer: str = "This is a grounded answer from fake LLM.",
        handler: Callable[[list[dict[str, str]]], str] | None = None,
        responses: list[str] | None = None,
    ) -> None:
        self.default_answer = default_answer
        self.handler = handler
        self.responses = list(responses) if responses is not None else None
        self.call_history: list[dict[str, Any]] = []

    def generate(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        self.call_history.append({
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        if self.handler:
            return self.handler(messages)
        if self.responses is not None and len(self.responses) > 0:
            return self.responses.pop(0)
        return self.default_answer

