"""Deterministic embedder for tests: no model, no external network download.

Each word is hashed to a bucket of a small vector, so texts that share words
get similar vectors. "Tokens" are whitespace-separated words plus two
special tokens, which lets tests produce over-limit input cheaply.
"""

from __future__ import annotations

import hashlib
import math

from backend.retrieval.embedder import Embedder


class FakeEmbedder(Embedder):
    """Deterministic hash-based embedder for fast unit tests."""

    def __init__(self, dimension: int = 384, max_tokens: int = 256, name: str = "fake-embedder") -> None:
        self._dimension = dimension
        self._max_tokens = max_tokens
        self._name = name
        self.document_calls: list[list[str]] = []
        self.query_calls: list[str] = []

    @property
    def model_name(self) -> str:
        return self._name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    def count_tokens(self, text: str) -> int:
        return len(text.split()) + 2  # + CLS and SEP

    def _encode(self, texts: list[str], *, is_query: bool) -> list[list[float]]:
        if is_query:
            self.query_calls.extend(texts)
        else:
            self.document_calls.append(list(texts))
        return [self._vector(t) for t in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        for word in text.lower().split():
            digest = hashlib.sha256(word.encode("utf-8")).digest()
            vector[int.from_bytes(digest[:4], "big") % self._dimension] += 1.0
        norm = math.sqrt(sum(x * x for x in vector))
        if norm == 0.0:  # empty text: a fixed unit vector keeps the contract (norm 1)
            vector[0] = 1.0
            return vector
        return [x / norm for x in vector]
