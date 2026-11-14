"""Page-aware text chunking (Stage 2).

Turns the per-page text produced by Stage 1 (`PageText`) into small chunks that
are suitable for embedding, without ever mixing two pages, so every chunk keeps
exactly one file name and one physical 1-based page number (needed for
citations, D-004 / D-005).

How a page is chunked
---------------------
1. Whitespace is normalised: every run of whitespace inside a paragraph
   (including a single line break, which in a PDF is usually just a line wrap)
   becomes one space. A blank line (two line breaks) is a paragraph break and
   is kept as `"\\n\\n"` inside a chunk.
2. The page is cut into *segments*, always using the largest unit that fits in
   `chunk_size`: a whole paragraph, otherwise its sentences, otherwise the
   words of an over-long sentence, otherwise (last resort) pieces of a single
   word that is longer than `chunk_size`.
3. Segments are packed one after another into a chunk until the next one would
   not fit. A chunk therefore ends on a paragraph, sentence or word boundary
   whenever that is possible.
4. Overlap: the next chunk starts with the last whole segment(s) of the
   previous chunk that fit in `overlap` characters (sentence-aligned when the
   sentences are short). If even the last segment is longer than `overlap`,
   the last whole words that fit are used instead. The overlap is shortened
   when needed so that it never prevents the next segment from fitting.

Sizes are measured in characters (D-002); the real token counts for the
embedding model are measured in Stage 3, so 800 / 120 are starting values,
not proven optimal ones. Only the standard library is used.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import accumulate, takewhile
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:  # only for type hints; keeps this module free of PyMuPDF imports
    from backend.ingestion.pdf_loader import PageText

DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 120
MIN_CHUNK_SIZE = 100

_PARAGRAPH_SEP = "\n\n"

# A blank line (possibly containing spaces) separates paragraphs.
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# Sentence ends followed by whitespace: Latin and Arabic/Urdu punctuation.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?\u06d4\u061f])\s+")
# CJK sentence ends are normally NOT followed by a space, so cut right after them.
_CJK_SENTENCE_BREAK = re.compile(r"(?<=[\u3002\uff01\uff1f])")


@dataclass(frozen=True)
class Chunk:
    """One searchable piece of a single PDF page, with its citation metadata."""

    chunk_id: str  # "<file_name>:<page_number>:<chunk_index>"
    file_name: str
    page_number: int  # physical page, 1-based (same as PageText)
    chunk_index: int  # 0-based, restarts at 0 on every page
    text: str


class _Segment(NamedTuple):
    text: str
    sep: str  # what is inserted before this segment when it follows another one


def validate_chunk_settings(chunk_size: int, overlap: int) -> None:
    """Raise if the chunking parameters are unusable.

    TypeError for a non-integer (booleans are rejected too), ValueError for an
    out-of-range value. Used by `chunk_pages()` and by `Settings`.
    """
    for name, value in (("chunk_size", chunk_size), ("overlap", overlap)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer, got {value!r}")
    if chunk_size < MIN_CHUNK_SIZE:
        raise ValueError(f"chunk_size must be at least {MIN_CHUNK_SIZE} characters, got {chunk_size}")
    if overlap < 0:
        raise ValueError(f"overlap must not be negative, got {overlap}")
    if overlap >= chunk_size:
        raise ValueError(f"overlap ({overlap}) must be smaller than chunk_size ({chunk_size})")


def chunk_pages(
    pages: Iterable[PageText],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
    *,
    max_tokens: int | None = None,
    token_counter: Callable[[str], int] | None = None,
) -> list[Chunk]:
    """Split every page into chunks of at most `chunk_size` characters (and at most `max_tokens` tokens).

    - Pages are processed independently; a chunk never contains text from two
      pages. Blank or whitespace-only pages produce no chunks.
    - `chunk_index` starts at 0 on every page; `chunk_id` is
      `"<file_name>:<page_number>:<chunk_index>"` (deterministic).
    - If `max_tokens` and `token_counter` are provided, chunk boundaries and
      sub-segments are guaranteed not to exceed the token limit.
    - The input objects are not modified.

    Raises ValueError/TypeError for invalid settings, and ValueError if the same
    (file_name, page_number) appears twice (the chunk ids would collide).
    """
    validate_chunk_settings(chunk_size, overlap)

    chunks: list[Chunk] = []
    seen: set[tuple[str, int]] = set()
    for page in pages:
        key = (page.file_name, page.page_number)
        if key in seen:
            raise ValueError(f"duplicate page in input: {page.file_name!r} page {page.page_number}")
        seen.add(key)
        for index, text in enumerate(
            _chunk_text(
                page.text,
                chunk_size,
                overlap,
                max_tokens=max_tokens,
                token_counter=token_counter,
            )
        ):
            chunks.append(
                Chunk(
                    chunk_id=f"{page.file_name}:{page.page_number}:{index}",
                    file_name=page.file_name,
                    page_number=page.page_number,
                    chunk_index=index,
                    text=text,
                )
            )
    return chunks


def _chunk_text(
    text: str,
    chunk_size: int,
    overlap: int,
    *,
    max_tokens: int | None = None,
    token_counter: Callable[[str], int] | None = None,
) -> list[str]:
    """Chunk the text of ONE page. Returns [] for blank text."""
    chunks: list[str] = []
    current: list[_Segment] = []
    current_len = 0
    for segment in _segments(text, chunk_size, max_tokens=max_tokens, token_counter=token_counter):
        added = len(segment.text) + (len(segment.sep) if current else 0)
        fits_chars = current_len + added <= chunk_size
        fits_tokens = True
        if token_counter is not None and max_tokens is not None:
            fits_tokens = token_counter(_render(current + [segment])) <= max_tokens

        if current and not (fits_chars and fits_tokens):
            chunks.append(_render(current))
            # The carried-over text must leave room for the new segment.
            room = chunk_size - len(segment.sep) - len(segment.text)
            current = _overlap_tail(current, min(overlap, room))
            if token_counter is not None and max_tokens is not None:
                while current and token_counter(_render(current + [segment])) > max_tokens:
                    current = current[1:]
            current_len = len(_render(current))
            added = len(segment.text) + (len(segment.sep) if current else 0)
        current.append(segment)
        current_len += added
    if current:
        chunks.append(_render(current))
    return chunks


def _render(segments: list[_Segment]) -> str:
    """Join segments; the first segment's own separator is not used."""
    return "".join(segment.text if i == 0 else segment.sep + segment.text for i, segment in enumerate(segments))


def _overlap_tail(segments: list[_Segment], budget: int) -> list[_Segment]:
    """The end of a finished chunk to repeat at the start of the next one.

    Prefers whole trailing segments (sentence/paragraph/word aligned) of at most
    `budget` characters; falls back to the last whole words of the final
    segment; returns [] if nothing fits or `budget` is 0.

    The tail is always shorter than the whole chunk (the caller's budget leaves
    room for the next segment), and pieces of a split long word are as long as
    the chunk size, so in practice they are never repeated as overlap.
    """
    if budget <= 0:
        return []

    # Whole trailing segments: the text from segment i to the end is its own
    # length plus the separators in between, so build the total from the back.
    n = len(segments)
    increments = [
        len(segment.text) + (len(segments[i + 1].sep) if i + 1 < n else 0) for i, segment in enumerate(segments)
    ]
    whole = _count_fitting(reversed(increments), budget)
    if whole:
        return segments[n - whole :]

    # Otherwise the last whole words of the final segment (a long sentence).
    words = segments[-1].text.split(" ")
    word_increments = [len(words[-1])] + [len(word) + 1 for word in reversed(words[:-1])]
    count = _count_fitting(word_increments, budget)
    return [_Segment(" ".join(words[len(words) - count :]), "")] if count else []


def _count_fitting(increments: Iterable[int], budget: int) -> int:
    """How many leading increments have a running total of at most `budget`."""
    return sum(1 for _ in takewhile(lambda total: total <= budget, accumulate(increments)))


def _segments(
    text: str,
    chunk_size: int,
    *,
    max_tokens: int | None = None,
    token_counter: Callable[[str], int] | None = None,
) -> list[_Segment]:
    """Cut a page into segments of at most `chunk_size` characters (and at most `max_tokens` tokens)."""
    segments: list[_Segment] = []

    def _fits(s: str) -> bool:
        if len(s) > chunk_size:
            return False
        if token_counter is not None and max_tokens is not None:
            return token_counter(s) <= max_tokens
        return True

    for paragraph in _paragraphs(text):
        if _fits(paragraph):
            segments.append(_Segment(paragraph, _PARAGRAPH_SEP))
            continue
        first = True
        for sentence, sep in _sentences(paragraph):
            sep = _PARAGRAPH_SEP if first else sep
            first = False
            if _fits(sentence):
                segments.append(_Segment(sentence, sep))
                continue
            for j, word in enumerate(sentence.split(" ")):
                word_sep = sep if j == 0 else " "
                if _fits(word):
                    segments.append(_Segment(word, word_sep))
                    continue
                for k, piece in enumerate(
                    _split_long_word(word, chunk_size, max_tokens=max_tokens, token_counter=token_counter)
                ):
                    segments.append(_Segment(piece, word_sep if k == 0 else ""))
    return segments


def _paragraphs(text: str) -> list[str]:
    """Paragraphs of the page, each with whitespace collapsed; no empty ones."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = (" ".join(raw.split()) for raw in _PARAGRAPH_BREAK.split(text))
    return [paragraph for paragraph in paragraphs if paragraph]


def _sentences(paragraph: str) -> list[tuple[str, str]]:
    """(sentence, separator-before-it) pairs; the first separator is a placeholder."""
    result: list[tuple[str, str]] = []
    for part in _SENTENCE_BREAK.split(paragraph):
        for k, sentence in enumerate(p for p in _CJK_SENTENCE_BREAK.split(part) if p):
            result.append((sentence, " " if k == 0 else ""))
    return result


def _split_long_word(
    word: str,
    size: int,
    *,
    max_tokens: int | None = None,
    token_counter: Callable[[str], int] | None = None,
) -> list[str]:
    """Last resort: cut a word longer than `size` into pieces of at most `size`.

    A cut never separates a combining mark (Unicode category M*) from the base
    character before it. Only if a whole window consists of marks is it cut at
    exactly `size`, so the size limit always holds.
    """
    pieces: list[str] = []
    start = 0
    while len(word) - start > size:
        end = start + size
        cut = end
        while cut > start and unicodedata.category(word[cut])[0] == "M":
            cut -= 1
        if cut == start:
            cut = end

        piece = word[start:cut]
        if token_counter is not None and max_tokens is not None:
            while len(piece) > 1 and token_counter(piece) > max_tokens:
                cut -= 1
                while cut > start and unicodedata.category(word[cut])[0] == "M":
                    cut -= 1
                if cut <= start:
                    cut = start + 1
                    break
                piece = word[start:cut]
        pieces.append(piece)
        start = cut

    remaining = word[start:]
    if remaining:
        if token_counter is not None and max_tokens is not None and token_counter(remaining) > max_tokens:
            while len(remaining) > 0 and token_counter(remaining) > max_tokens:
                sub_cut = max(1, len(remaining) // 2)
                while sub_cut > 1 and token_counter(remaining[:sub_cut]) > max_tokens:
                    sub_cut -= 1
                pieces.append(remaining[:sub_cut])
                remaining = remaining[sub_cut:]
        if remaining:
            pieces.append(remaining)
    return pieces
