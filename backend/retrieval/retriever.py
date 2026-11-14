"""Semantic retriever (Stage 4).

Wraps embedding + ChromaDB query in one operation:

    retrieve(query, top_k, min_similarity) -> list[RetrievedChunk]

``RetrievedChunk`` is defined in ``vector_store`` and carries the
chunk text, source metadata and similarity score.

Design decisions
----------------
D-039 — The retriever is a plain function, not a class. Only one
  public operation exists (retrieve), so a class would add boilerplate
  with no benefit.
D-040 — ``min_similarity`` defaults to 0.0 so that callers get all
  cosine-similar results without any extra filter unless they opt in.
D-041 — ``QueryTooLong`` extends ``ValueError`` and carries the actual
  and maximum token counts so the API layer can build a precise 422
  response without re-parsing the string message.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.config import settings
from backend.retrieval import services
from backend.retrieval.vector_store import RetrievedChunk

if TYPE_CHECKING:
    from backend.retrieval.embedder import Embedder
    from backend.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class QueryTooLong(ValueError):
    """The query exceeds the model's token limit.

    Attributes
    ----------
    token_count:
        Actual number of tokens the query produces.
    max_tokens:
        The model's hard upper bound.
    """

    def __init__(self, token_count: int, max_tokens: int) -> None:
        self.token_count = token_count
        self.max_tokens = max_tokens
        super().__init__(
            f"Query is {token_count} tokens; limit is {max_tokens}. "
            "Please shorten the question."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def retrieve(
    query: str,
    top_k: int | None = None,
    min_similarity: float | None = None,
    *,
    file_names: list[str] | None = None,
    embedder: "Embedder | None" = None,
    store: "VectorStore | None" = None,
) -> list[RetrievedChunk]:
    """Embed *query*, search the vector store, filter by similarity.

    Parameters
    ----------
    query:
        The natural-language question or search string.
    top_k:
        Maximum number of results to return. Defaults to
        ``settings.retrieval_top_k`` (env ``RETRIEVAL_TOP_K``).
    min_similarity:
        Discard results whose cosine similarity is below this threshold.
        Defaults to ``settings.min_similarity`` (env ``MIN_SIMILARITY``).
    embedder:
        Override the embedder singleton. Injected by tests via the
        ``isolated_chroma`` autouse fixture; production code passes ``None``.
    store:
        Override the vector-store singleton. Same injection pattern.

    Returns
    -------
    list[RetrievedChunk]
        Matching chunks ordered by descending similarity, filtered to
        those above *min_similarity*.

    Raises
    ------
    ValueError
        If *query* is empty/whitespace, *top_k* < 1, or *min_similarity*
        is outside [-1.0, 1.0].
    QueryTooLong
        If the query produces more tokens than the embedder can handle.
    """
    # ----- validate inputs -------------------------------------------------
    if not query or not query.strip():
        raise ValueError("Query must not be empty.")

    resolved_top_k: int = top_k if top_k is not None else settings.retrieval_top_k
    resolved_min_sim: float = (
        min_similarity if min_similarity is not None else settings.min_similarity
    )

    if resolved_top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {resolved_top_k}.")
    if not (-1.0 <= resolved_min_sim <= 1.0):
        raise ValueError(
            f"min_similarity must be in [-1.0, 1.0], got {resolved_min_sim}."
        )

    # ----- resolve singletons ----------------------------------------------
    _embedder = embedder if embedder is not None else services.get_embedder()
    _store = store if store is not None else services.get_store()

    # ----- token-limit check -----------------------------------------------
    token_count = _embedder.count_tokens(query)
    if token_count > _embedder.max_tokens:
        raise QueryTooLong(token_count, _embedder.max_tokens)

    # ----- embed and search ------------------------------------------------
    query_vector = _embedder.embed_query(query)
    raw_results: list[RetrievedChunk] = _store.query(
        query_vector, top_k=resolved_top_k, file_names=file_names
    )

    # ----- filter by similarity --------------------------------------------
    filtered = [r for r in raw_results if r.similarity >= resolved_min_sim]

    logger.debug(
        "retrieve '%s…': %d/%d results above similarity %.3f",
        query[:50],
        len(filtered),
        len(raw_results),
        resolved_min_sim,
    )
    return filtered

