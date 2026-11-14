"""Embedder interface (Stage 3B, decision 9.2 #9).

Turning text into vectors is kept separate from storing vectors, so the store
never needs to know which model produced them. Rules every embedder follows:

- vectors are L2-normalised (cosine similarity = dot product);
- a text longer than the model's token limit is NEVER silently truncated:
  `TokenLimitExceeded` is raised *before* any embedding is computed;
- documents and queries use separate methods (a future model may need
  different prefixes for each).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass


class TokenLimitExceeded(ValueError):
    """One or more texts are longer than the model can embed without truncation."""

    def __init__(self, over_limit: dict[int, int], max_tokens: int) -> None:
        self.over_limit = dict(over_limit)  # input position -> token count
        self.max_tokens = max_tokens
        worst = max(self.over_limit.values())
        super().__init__(
            f"{len(self.over_limit)} text(s) exceed the {max_tokens}-token limit "
            f"(longest: {worst} tokens); refusing to truncate silently."
        )


@dataclass(frozen=True)
class EmbeddedChunk:
    """A vector together with the token count of the text it was made from."""

    vector: list[float]
    token_count: int


class Embedder(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def dimension(self) -> int: ...

    @property
    @abstractmethod
    def max_tokens(self) -> int:
        """Largest input, in tokens INCLUDING special tokens (CLS/SEP)."""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Tokens the model would see for `text`, special tokens included."""

    @abstractmethod
    def _encode(self, texts: list[str], *, is_query: bool) -> list[list[float]]:
        """Raw embedding of texts already checked against the token limit."""

    def check_limits(self, texts: list[str]) -> list[int]:
        """Token count per text; raises TokenLimitExceeded if any is over the limit."""
        counts = [self.count_tokens(t) for t in texts]
        over = {i: c for i, c in enumerate(counts) if c > self.max_tokens}
        if over:
            raise TokenLimitExceeded(over, self.max_tokens)
        return counts

    def embed_documents(self, texts: list[str]) -> list[EmbeddedChunk]:
        if not texts:
            return []
        counts = self.check_limits(texts)
        vectors = self._encode(texts, is_query=False)
        return self._validated(texts, vectors, counts)

    def embed_query(self, text: str) -> list[float]:
        counts = self.check_limits([text])
        vectors = self._encode([text], is_query=True)
        return self._validated([text], vectors, counts)[0].vector

    def _validated(
        self, texts: list[str], vectors: list[list[float]], counts: list[int]
    ) -> list[EmbeddedChunk]:
        if len(vectors) != len(texts):
            raise RuntimeError(f"Embedder returned {len(vectors)} vectors for {len(texts)} texts.")
        for vector in vectors:
            check_normalized(vector, self.dimension)
        return [EmbeddedChunk(list(map(float, v)), c) for v, c in zip(vectors, counts)]


def check_normalized(vector, dimension: int, tolerance: float = 1e-3) -> None:
    """Raise ValueError unless `vector` has `dimension` finite values and unit length."""
    if len(vector) != dimension:
        raise ValueError(f"Vector has {len(vector)} values, expected {dimension}.")
    if not all(math.isfinite(x) for x in vector):
        raise ValueError("Vector contains NaN or infinity.")
    norm = math.sqrt(sum(x * x for x in vector))
    if abs(norm - 1.0) > tolerance:
        raise ValueError(f"Vector is not normalised (L2 norm {norm:.6f}).")
