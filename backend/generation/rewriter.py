"""Conversational follow-up query reformulation (Stage 7).

Rewrites follow-up questions referencing past conversational context
(e.g., "What is its battery life?") into standalone, self-contained
search queries (e.g., "What is the battery life of Model A-100?")
for accurate semantic retrieval.

Decision Reference: D-006 (Follow-up questions are rewritten into standalone
questions with one extra LLM call; previous assistant answers are never evidence).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from backend.generation.llm_client import GroqClient, LLMClient

if TYPE_CHECKING:
    from backend.conversation.store import MessageRecord

logger = logging.getLogger(__name__)

REWRITE_SYSTEM_PROMPT = """You are an expert query reformulation assistant for a document retrieval engine.
Your task is to rewrite a follow-up question into a clear, self-contained search query using the conversation history.

STRICT OPERATING RULES:
1. RESOLVE REFERENCES: Replace all pronouns ("it", "its", "they", "this", "that") and referential phrases ("that model", "the first one", "the earlier policy") with the specific entity names or topics established in the conversation history.
2. PRESERVE INTENT: Do not change the core question or intent.
3. DO NOT ANSWER: Do NOT attempt to answer the question or evaluate claims.
4. DO NOT ASSUME FACTS: Do not introduce external facts or unnecessary constraints.
5. STANDALONE UNCHANGED: If the question is already fully self-contained and makes sense without conversation context, return it exactly as is.
6. OUTPUT FORMAT: Output ONLY the rewritten standalone question. Do NOT include quotes, introductory text, explanations, or labels like "Rewritten query:".
"""

REWRITE_USER_PROMPT_TEMPLATE = """Conversation History:
{history}

Current Question: {question}

Standalone Query:"""


def format_history_for_rewriter(messages: list[MessageRecord], max_turns: int = 5) -> str:
    """Format recent turns into a structured history block."""
    if not messages:
        return ""

    # Each turn has up to 2 messages (user + assistant)
    slice_count = max_turns * 2 if max_turns > 0 else len(messages)
    recent = messages[-slice_count:]
    lines = []
    for m in recent:
        content_clean = m.content.strip().replace("\n", " ")
        if not content_clean:
            continue
        role_label = "User" if m.role == "user" else "Assistant"
        lines.append(f"{role_label}: {content_clean}")
    return "\n".join(lines)


def clean_rewritten_query(raw_query: str, fallback_query: str) -> str:
    """Clean LLM output from markdown quotes and label prefixes."""
    cleaned = raw_query.strip()
    if not cleaned:
        return fallback_query.strip()

    # Remove quotes
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        cleaned = cleaned[1:-1].strip()

    # Remove common prefixes
    lower = cleaned.lower()
    for prefix in (
        "standalone query:",
        "rewritten query:",
        "rewritten question:",
        "query:",
    ):
        if lower.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
            break

    return cleaned if cleaned else fallback_query.strip()


def rewrite_query(
    question: str,
    history: list[MessageRecord],
    *,
    llm_client: LLMClient | None = None,
    max_turns: int = 5,
) -> str:
    """Rewrite a conversational question into a standalone query.
    
    If history is empty or formatted history is blank, returns the original question.
    """
    cleaned_question = question.strip()
    if not cleaned_question:
        return ""

    if not history:
        return cleaned_question

    history_str = format_history_for_rewriter(history, max_turns=max_turns)
    if not history_str.strip():
        return cleaned_question

    user_content = REWRITE_USER_PROMPT_TEMPLATE.format(
        history=history_str,
        question=cleaned_question,
    )
    messages = [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    client = llm_client or GroqClient()
    try:
        raw_response = client.generate(messages, temperature=0.0)
        rewritten = clean_rewritten_query(raw_response, fallback_query=cleaned_question)
        logger.info("Rewrote query '%s' -> '%s'", cleaned_question, rewritten)
        return rewritten
    except Exception as exc:
        logger.warning("Query rewriting failed (%s). Falling back to original question.", exc)
        return cleaned_question

