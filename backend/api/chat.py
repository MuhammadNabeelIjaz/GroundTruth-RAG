"""POST /chat / POST /answer endpoint (Stage 5).

Answers user questions grounded in indexed PDF documents using Groq LLM.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from backend.api.search import _make_excerpt
from backend.config import settings
from backend.conversation.store import ConversationNotFoundError
from backend.generation.answer_service import answer_question
from backend.generation.llm_client import (
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from backend.retrieval.retriever import QueryTooLong
from backend.schemas import AnswerRequest, AnswerResponse, SourceCitation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generation"])


@router.post("/answer", response_model=AnswerResponse)
@router.post("/chat", response_model=AnswerResponse)
def get_grounded_answer(request: AnswerRequest) -> AnswerResponse:
    """Generate a grounded answer to *question* using retrieved document chunks.

    Returns:
        AnswerResponse with answer text, boolean `found`, and source citations.
    """
    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")

    if request.top_k is not None and not (1 <= request.top_k <= 100):
        raise HTTPException(status_code=422, detail="top_k must be between 1 and 100.")
    if request.min_similarity is not None and not (-1.0 <= request.min_similarity <= 1.0):
        raise HTTPException(status_code=422, detail="min_similarity must be between -1.0 and 1.0.")

    try:
        result = answer_question(
            request.question,
            top_k=request.top_k,
            min_similarity=request.min_similarity,
            file_names=request.file_names,
            conversation_id=request.conversation_id,
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except QueryTooLong as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMAuthError as exc:
        logger.error("Authentication error during answer generation: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM authentication error: {exc}") from exc
    except LLMRateLimitError as exc:
        logger.warning("Rate limit hit during answer generation: %s", exc)
        raise HTTPException(status_code=429, detail="LLM rate limit reached. Please retry later.") from exc
    except (LLMTimeoutError, LLMConnectionError) as exc:
        logger.error("LLM connection timeout/failure: %s", exc)
        raise HTTPException(status_code=504, detail="LLM provider timed out or unreachable.") from exc
    except LLMResponseError as exc:
        logger.error("LLM invalid response: %s", exc)
        raise HTTPException(status_code=502, detail="LLM provider returned an invalid response.") from exc

    citations = [
        SourceCitation(
            chunk_id=c.chunk_id,
            file_name=c.file_name,
            page_number=c.page_number,
            chunk_index=c.chunk_index,
            similarity=round(c.similarity, 6),
            excerpt=c.excerpt,
        )
        for c in result.citations
    ]

    return AnswerResponse(
        question=result.question,
        answer=result.answer,
        found=result.found,
        sources=citations,
        conversation_id=result.conversation_id,
        standalone_query=result.standalone_query,
    )
