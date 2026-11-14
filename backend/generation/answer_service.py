"""Grounded answer generation service (Stage 5, updated Stage 6 & 7).

Coordinates:
  User Question
  [-> Conversation Store & Query Rewriter (Stage 7)]
  -> Stage 4 Retriever
  -> Grounded Prompts
  -> LLMClient
  -> Citation Validation (Stage 6)
  [-> Conversation Persistence (Stage 7)]
  -> AnswerResult
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from backend.config import settings
from backend.conversation.store import (
    ConversationNotFoundError,
    SQLiteConversationStore,
    get_conversation_store,
)
from backend.generation.citations import (
    ValidatedCitation,
    extract_cited_passage_indices,
    validate_citations,
)
from backend.generation.llm_client import GroqClient, LLMClient
from backend.generation.prompts import build_messages
from backend.generation.rewriter import rewrite_query
from backend.retrieval.retriever import retrieve
from backend.retrieval.vector_store import RetrievedChunk

if TYPE_CHECKING:
    from backend.retrieval.embedder import Embedder
    from backend.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Phrases signaling the model could not answer from the provided documents.
_REFUSAL_PHRASES = (
    "do not contain sufficient information",
    "does not contain sufficient information",
    "not contain sufficient information",
    "not enough information",
    "insufficient information",
    "cannot answer",
    "unable to answer",
    "no information provided",
    "not mentioned in the provided",
    "not mentioned in the text",
    "none of the provided",
    "no mention of",
    "not provided in the",
    "documents do not mention",
    "passages do not mention",
    "not discussed",
    "text does not contain",
    "context does not provide",
    "could not find any information",
)

_FRAMING_PREFIXES = (
    "based on the provided documents,",
    "based on the provided document,",
    "based on the provided text,",
    "according to the provided documents,",
    "according to the documents,",
    "the provided documents",
    "the provided document",
    "the provided text",
    "the context",
)


def is_refusal_answer(raw_answer: str, chunks: list[RetrievedChunk]) -> bool:
    """Determine whether the generated response is a genuine refusal to answer.

    Applies conservative multi-stage evaluation to distinguish genuine refusals
    from affirmative answers that contain secondary caveats.
    """
    answer_lower = raw_answer.lower().strip()
    has_refusal = any(phrase in answer_lower for phrase in _REFUSAL_PHRASES)
    if not has_refusal:
        return False

    cited_indices = extract_cited_passage_indices(raw_answer, len(chunks))
    if not cited_indices:
        return True

    # Check if a citation is itself the subject of a refusal predicate:
    # e.g., "[Passage 1] does not contain sufficient information..."
    citation_refusal_pattern = r"\[(?:passage\s+)?\d+\]\s+(?:does|do)\s+not\s+(?:contain|mention|provide|have)"
    if re.search(citation_refusal_pattern, answer_lower):
        citations_count = len(re.findall(r"\[(?:passage\s+)?\d+\]", answer_lower))
        refusal_citations_count = len(re.findall(citation_refusal_pattern, answer_lower))
        if refusal_citations_count >= citations_count:
            return True

    # Strip opening concessive clause if present: 'While/Although ..., '
    main_text = re.sub(r"^(?:while|although)\s+[^,]+,\s*", "", answer_lower)

    # Inspect the primary clause of the main statement (before 'however', 'but', period, semicolon, newline)
    first_split = re.split(r"[.;\n]|\b(?:however|but)\b", main_text)[0].strip()
    cleaned_opening = first_split
    for prefix in _FRAMING_PREFIXES:
        if cleaned_opening.startswith(prefix):
            cleaned_opening = cleaned_opening[len(prefix):].strip()

    # If the opening clause itself asserts insufficiency without affirmative cited facts:
    if any(phrase in cleaned_opening for phrase in _REFUSAL_PHRASES):
        if not re.search(r"\[(?:passage\s+)?\d+\]", first_split):
            return True

    # Conservative default: Affirmative cited facts exist
    return False


@dataclass(frozen=True)
class AnswerResult:
    """The result of a grounded question-answering query."""

    question: str
    answer: str
    found: bool
    retrieved_chunks: list[RetrievedChunk]
    citations: list[ValidatedCitation]
    conversation_id: str | None = None
    standalone_query: str | None = None


def answer_question(
    question: str,
    top_k: int | None = None,
    min_similarity: float | None = None,
    *,
    file_names: list[str] | None = None,
    conversation_id: str | None = None,
    conversation_store: SQLiteConversationStore | None = None,
    llm_client: LLMClient | None = None,
    embedder: Embedder | None = None,
    store: VectorStore | None = None,
) -> AnswerResult:
    """Retrieve relevant chunks and generate a grounded answer."""
    if not question or not question.strip():
        raise ValueError("Question must not be empty.")

    cleaned_question = question.strip()
    client = llm_client or GroqClient()
    c_store = conversation_store or (get_conversation_store() if conversation_id else None)

    # 1. Conversational Query Reformulation (Stage 7)
    standalone_query = cleaned_question
    if conversation_id:
        assert c_store is not None
        conv = c_store.get_conversation(conversation_id)
        if not conv:
            raise ConversationNotFoundError(conversation_id)

        history = c_store.get_messages(
            conversation_id,
            limit=settings.max_history_turns * 2,
        )
        if history:
            standalone_query = rewrite_query(
                cleaned_question,
                history,
                llm_client=client,
                max_turns=settings.max_history_turns,
            )

    # 2. Retrieve chunks using Stage 4 retriever with the standalone query
    chunks = retrieve(
        standalone_query,
        top_k=top_k,
        min_similarity=min_similarity,
        file_names=file_names,
        embedder=embedder,
        store=store,
    )

    # 3. If no chunks found, return immediate refusal without invoking generation LLM
    if not chunks:
        refusal_text = "The provided documents do not contain sufficient information to answer this question."
        if c_store is not None:
            c_store.add_message(
                conversation_id,
                role="user",
                content=cleaned_question,
                standalone_query=standalone_query,
            )
            c_store.add_message(
                conversation_id,
                role="assistant",
                content=refusal_text,
                found=False,
                sources=[],
            )

        return AnswerResult(
            question=cleaned_question,
            answer=refusal_text,
            found=False,
            retrieved_chunks=[],
            citations=[],
            conversation_id=conversation_id,
            standalone_query=standalone_query,
        )

    # 4. Build grounded messages and call LLM
    messages = build_messages(standalone_query, chunks)
    raw_answer = client.generate(messages)

    # 5. Check whether answer is a refusal
    is_refusal = is_refusal_answer(raw_answer, chunks)

    # 6. Validate citations (Stage 6)
    validated_citations = validate_citations(
        raw_answer,
        chunks,
        is_refusal=is_refusal,
    )

    # 7. Persist to Conversation Store (Stage 7)
    if c_store is not None:
        c_store.add_message(
            conversation_id,
            role="user",
            content=cleaned_question,
            standalone_query=standalone_query,
        )
        sources_data = [
            {
                "chunk_id": c.chunk_id,
                "file_name": c.file_name,
                "page_number": c.page_number,
                "chunk_index": c.chunk_index,
                "similarity": round(c.similarity, 6),
                "excerpt": c.excerpt,
            }
            for c in validated_citations
        ]
        c_store.add_message(
            conversation_id,
            role="assistant",
            content=raw_answer,
            standalone_query=standalone_query,
            found=not is_refusal,
            sources=sources_data,
        )

    return AnswerResult(
        question=cleaned_question,
        answer=raw_answer,
        found=not is_refusal,
        retrieved_chunks=chunks,
        citations=validated_citations,
        conversation_id=conversation_id,
        standalone_query=standalone_query,
    )
