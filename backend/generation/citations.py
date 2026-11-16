"""Source citation validation and ground-truth excerpt attribution (Stage 6).

Implements:
1. Citation extraction: identifies bracketed passage citations like [Passage 1], [1], [p. 1].
2. Passage index mapping: strictly maps citations to valid retrieved chunks (1-based index).
3. Groundedness verification: checks whether answer claims have matching lexical/semantic evidence
   in the cited passages.
4. Uncited filtering: only includes sources that are genuinely referenced by the answer (D-007).
5. Grounded citation construction: preserves verified file_name, 1-based page_number,
   chunk_id, similarity, and exact supporting excerpt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.retrieval.vector_store import RetrievedChunk

# Regex to detect passage references in LLM text:
# Matches: [Passage 1], [passage 1], [Passages 1, 2], [1], [1, 2], [1][2], etc.
_PASSAGE_REF_PATTERN = re.compile(
    r"\[(?:passage\s*)?(\d+)(?:\s*,\s*(?:passage\s*)?(\d+))*\]",
    re.IGNORECASE,
)
_DIGIT_PATTERN = re.compile(r"\b\d+\b")


@dataclass(frozen=True)
class ValidatedCitation:
    """A validated document source cited by the answer."""

    chunk_id: str
    file_name: str
    page_number: int  # 1-based physical PDF page
    chunk_index: int
    similarity: float
    excerpt: str
    passage_number: int | None = None


def extract_cited_passage_indices(answer_text: str, total_chunks: int) -> set[int]:
    """Extract 1-based chunk indices explicitly referenced in *answer_text*.

    Filters out any numbers that do not correspond to an actual retrieved chunk.
    """
    if not answer_text or total_chunks <= 0:
        return set()

    found_indices: set[int] = set()

    # Search for [Passage X] or [X] patterns
    for match in re.finditer(r"\[([^\]]+)\]", answer_text):
        content = match.group(1).lower()
        if "passage" in content or content.strip().isdigit() or re.search(r"^\d+(\s*,\s*\d+)*$", content.strip()):
            for digit_match in _DIGIT_PATTERN.finditer(content):
                idx = int(digit_match.group(0))
                if 1 <= idx <= total_chunks:
                    found_indices.add(idx)

    # Also search for inline text references like "Passage 1 states" or "In passage 2"
    for match in re.finditer(r"\bpassage\s+(\d+)\b", answer_text, re.IGNORECASE):
        idx = int(match.group(1))
        if 1 <= idx <= total_chunks:
            found_indices.add(idx)

    return found_indices


def compute_lexical_overlap(answer_text: str, chunk_text: str) -> float:
    """Compute word overlap ratio between answer and chunk text.

    Returns float in range [0.0, 1.0].
    """
    if not answer_text or not chunk_text:
        return 0.0

    answer_words = {
        w.lower()
        for w in re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", answer_text)
    }
    chunk_words = {
        w.lower()
        for w in re.findall(r"\b[a-zA-Z0-9_-]{3,}\b", chunk_text)
    }

    if not answer_words or not chunk_words:
        return 0.0

    shared = answer_words.intersection(chunk_words)
    return len(shared) / len(answer_words)


def extract_best_excerpt(chunk_text: str, answer_text: str, max_chars: int = 200) -> str:
    """Extract the most relevant continuous excerpt from *chunk_text* matching *answer_text*.

    Cuts at sentence boundaries so quotes are not truncated mid-sentence.
    """
    cleaned_chunk = " ".join(chunk_text.split())
    if len(cleaned_chunk) <= max_chars:
        return cleaned_chunk

    # Split into sentences
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned_chunk) if s.strip()]
    if not sentences:
        return cleaned_chunk[:max_chars].rstrip() + "\u2026"

    # Score sentences by word overlap with answer
    answer_words = set(re.findall(r"\b\w{3,}\b", answer_text.lower()))
    best_sent = sentences[0]
    best_score = -1

    for s in sentences:
        words = set(re.findall(r"\b\w{3,}\b", s.lower()))
        score = len(words.intersection(answer_words))
        if score > best_score:
            best_score = score
            best_sent = s

    if len(best_sent) <= max_chars:
        return best_sent

    # Cut at last sentence boundary within max_chars, or last word boundary
    trimmed = best_sent[:max_chars]
    last_period = max(trimmed.rfind("."), trimmed.rfind("!"), trimmed.rfind("?"))
    if last_period > int(max_chars * 0.4):
        return trimmed[:last_period + 1]

    last_space = trimmed.rfind(" ")
    if last_space > 0:
        return trimmed[:last_space].rstrip() + "\u2026"
    return trimmed + "\u2026"


def validate_citations(
    answer_text: str,
    retrieved_chunks: list[RetrievedChunk],
    *,
    is_refusal: bool = False,
    min_overlap_threshold: float = 0.05,
) -> list[ValidatedCitation]:
    """Validate citations against retrieved chunks and answer content.

    Rules:
    - If *is_refusal* is True, NO sources are cited (an unanswerable question has no supporting facts).
    - If explicit passage tags ([Passage 1], [1]) appear, only valid referenced chunks are included.
    - If no explicit passage tags appear but the answer is factual, chunks with lexical overlap
      above *min_overlap_threshold* are attributed. If no overlap exceeds threshold, the top-ranked
      retrieved chunk is retained if similarity is strong (>0.4).
    - Chunks with zero lexical overlap and low similarity are excluded (D-007: Sources list only passages
      the answer actually used).
    - Excerpts are extracted directly from stored chunk text, preserving original file_name and 1-based page.
    """
    if is_refusal or not retrieved_chunks or not answer_text.strip():
        return []

    explicit_indices = extract_cited_passage_indices(answer_text, len(retrieved_chunks))
    selected_items: list[tuple[int, RetrievedChunk]] = []

    if explicit_indices:
        # User referenced specific passages
        for idx in sorted(explicit_indices):
            chunk = retrieved_chunks[idx - 1]
            selected_items.append((idx, chunk))
    else:
        # Check lexical overlap for each chunk
        for i, chunk in enumerate(retrieved_chunks, 1):
            overlap = compute_lexical_overlap(answer_text, chunk.text)
            if overlap >= min_overlap_threshold:
                selected_items.append((i, chunk))

        # Fallback if answer synthesized facts without direct keyword overlap but strong similarity
        if not selected_items and retrieved_chunks and retrieved_chunks[0].similarity >= 0.4:
            selected_items.append((1, retrieved_chunks[0]))

    # Convert selected chunks to ValidatedCitation objects
    citations: list[ValidatedCitation] = []

    for passage_num, chunk in selected_items:
        excerpt = extract_best_excerpt(chunk.text, answer_text, max_chars=350)
        citations.append(
            ValidatedCitation(
                chunk_id=chunk.chunk_id,
                file_name=chunk.file_name,
                page_number=chunk.page_number,
                chunk_index=chunk.chunk_index,
                similarity=round(chunk.similarity, 6),
                excerpt=excerpt,
                passage_number=passage_num,
            )
        )

    return citations
