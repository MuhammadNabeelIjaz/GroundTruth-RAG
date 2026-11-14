"""API router for multi-turn conversations (Stage 7).

Endpoints:
- POST   /conversations: Create a new conversation session
- GET    /conversations: List conversations ordered by recent activity
- GET    /conversations/{conversation_id}: Retrieve conversation history
- DELETE /conversations/{conversation_id}: Delete conversation and its history
- POST   /conversations/{conversation_id}/messages: Ask follow-up question
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from backend.conversation.store import (
    ConversationNotFoundError,
    get_conversation_store,
)
from backend.generation.answer_service import answer_question
from backend.generation.llm_client import (
    LLMAuthError,
    LLMConnectionError,
    LLMRateLimitError,
    LLMResponseError,
    LLMTimeoutError,
)
from backend.retrieval.retriever import QueryTooLong
from backend.schemas import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMessageRequest,
    ConversationMessageResponse,
    ConversationResponse,
    MessageItem,
    SourceCitation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConversationResponse)
def create_conversation(
    request: ConversationCreateRequest | None = None,
) -> ConversationResponse:
    """Create a new conversation session."""
    title = request.title if request else None
    store = get_conversation_store()
    conv = store.create_conversation(title=title)
    return ConversationResponse(
        conversation_id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=0,
    )


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ConversationListResponse:
    """List conversations ordered by most recently updated."""
    store = get_conversation_store()
    items = store.list_conversations(limit=limit, offset=offset)
    total = store.count_conversations()
    return ConversationListResponse(
        total=total,
        conversations=[
            ConversationResponse(
                conversation_id=c.id,
                title=c.title,
                created_at=c.created_at,
                updated_at=c.updated_at,
                message_count=c.message_count,
            )
            for c in items
        ],
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation_history(conversation_id: str) -> ConversationDetailResponse:
    """Retrieve full message history for a conversation."""
    store = get_conversation_store()
    conv = store.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found.",
        )

    messages = store.get_messages(conversation_id)
    msg_items: list[MessageItem] = []
    for m in messages:
        citations = [
            SourceCitation(
                chunk_id=s["chunk_id"],
                file_name=s["file_name"],
                page_number=s["page_number"],
                chunk_index=s["chunk_index"],
                similarity=s["similarity"],
                excerpt=s["excerpt"],
            )
            for s in m.sources
        ]
        msg_items.append(
            MessageItem(
                id=m.id,
                conversation_id=m.conversation_id,
                role=m.role,
                content=m.content,
                standalone_query=m.standalone_query,
                found=m.found,
                sources=citations,
                created_at=m.created_at,
            )
        )

    return ConversationDetailResponse(
        conversation_id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        message_count=conv.message_count,
        messages=msg_items,
    )


@router.delete("/{conversation_id}", response_model=dict[str, bool | str])
def delete_conversation(conversation_id: str) -> dict[str, bool | str]:
    """Delete a conversation and its messages."""
    store = get_conversation_store()
    deleted = store.delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found.",
        )
    return {"conversation_id": conversation_id, "deleted": True}


@router.post("/{conversation_id}/messages", response_model=ConversationMessageResponse)
def send_conversation_message(
    conversation_id: str,
    request: ConversationMessageRequest,
) -> ConversationMessageResponse:
    """Send a question within a conversation and receive a grounded answer."""
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
            conversation_id=conversation_id,
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

    # Retrieve created_at timestamp from the assistant's saved message
    store = get_conversation_store()
    latest_msgs = store.get_messages(conversation_id, limit=1)
    msg_created_at = latest_msgs[0].created_at if latest_msgs else ""

    return ConversationMessageResponse(
        conversation_id=conversation_id,
        question=result.question,
        standalone_query=result.standalone_query or result.question,
        answer=result.answer,
        found=result.found,
        sources=citations,
        created_at=msg_created_at,
    )

