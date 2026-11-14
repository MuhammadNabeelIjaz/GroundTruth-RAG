"""POST /search endpoint (Stage 4).

Takes a natural-language *query*, embeds it, searches ChromaDB and returns
the most relevant chunks with source metadata and a short excerpt.

Error mapping
-------------
400 — empty or whitespace-only query.
422 — out-of-range ``top_k``/``min_similarity``, or query too long for the
      embedding model.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.retrieval.retriever import QueryTooLong, retrieve
from backend.schemas import SearchRequest, SearchResponse, SearchResultItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])

# How many characters to include in the excerpt field.
_EXCERPT_CHARS = 200


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_excerpt(text: str) -> str:
    """Return the first ``_EXCERPT_CHARS`` characters of *text*, collapsed."""
    collapsed = " ".join(text.split())
    if len(collapsed) <= _EXCERPT_CHARS:
        return collapsed
    return collapsed[:_EXCERPT_CHARS] + "\u2026"  # U+2026 HORIZONTAL ELLIPSIS


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("", response_model=SearchResponse)
def search_documents(request: SearchRequest) -> SearchResponse:
    r"""Search the vector index for chunks relevant to *query*.

    **Request body** (JSON):

    | Field | Type | Default | Description |
    |---|---|---|---|
    | ``query`` | string | required | Natural-language question or keywords |
    | ``top_k`` | int \| null | server default (5) | Maximum results (1–100) |
    | ``min_similarity`` | float \| null | server default (0.0) | Minimum cosine similarity (−1.0–1.0) |

    **Response** (200):
    ```json
    {
      "query": "...",
      "total_found": 3,
      "results": [
        {
          "chunk_id": "...",
          "file_name": "example.pdf",
          "page_number": 2,
          "chunk_index": 0,
          "text": "...",
          "similarity": 0.87,
          "excerpt": "..."
        }
      ]
    }
    ```
    """
    # Validate query string before calling retriever so we get 400, not 422.
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    # Validate numeric fields here too so we surface them as 422 with a clear
    # message even before the retriever raises.
    if request.top_k is not None and not (1 <= request.top_k <= 100):
        raise HTTPException(
            status_code=422, detail="top_k must be between 1 and 100."
        )
    if request.min_similarity is not None and not (
        -1.0 <= request.min_similarity <= 1.0
    ):
        raise HTTPException(
            status_code=422,
            detail="min_similarity must be between -1.0 and 1.0.",
        )

    try:
        chunks = retrieve(
            request.query,
            top_k=request.top_k,
            min_similarity=request.min_similarity,
        )
    except QueryTooLong as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    items = [
        SearchResultItem(
            chunk_id=c.chunk_id,
            file_name=c.file_name,
            page_number=c.page_number,
            chunk_index=c.chunk_index,
            text=c.text,
            similarity=round(c.similarity, 6),
            excerpt=_make_excerpt(c.text),
        )
        for c in chunks
    ]
    return SearchResponse(
        query=request.query,
        total_found=len(items),
        results=items,
    )

