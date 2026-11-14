"""Tests for backend/ingestion/chunker.py (Stage 2).

Everything is pure Python: no files, no network, no model. The PDF round trip at
the end generates its PDF in code inside pytest's temporary directory.

Helper sentences: `S(n)` is always 21 characters ("Sentence 001 is here."),
which makes the expected chunk contents easy to calculate by hand.
"""

import random
import re
import unicodedata
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest

from backend.ingestion import chunker
from backend.ingestion.chunker import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    MIN_CHUNK_SIZE,
    Chunk,
    chunk_pages,
    validate_chunk_settings,
)
from backend.ingestion.pdf_loader import PageText, extract_pages


def page(text: str, number: int = 1, name: str = "policy.pdf") -> PageText:
    return PageText(file_name=name, page_number=number, text=text)


def chunk_texts(text: str, size: int = 100, overlap: int = 0) -> list[str]:
    return [c.text for c in chunk_pages([page(text)], size, overlap)]


def S(n: int) -> str:
    return f"Sentence {n:03d} is here."


def sentences(first: int, last: int) -> str:
    return " ".join(S(n) for n in range(first, last + 1))


def no_space(text: str) -> str:
    return "".join(text.split())


def is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    it = iter(haystack)
    return all(token in it for token in needle)


# --------------------------------------------------------------------------
# Settings validation
# --------------------------------------------------------------------------


def test_defaults_are_the_approved_starting_values():
    assert (DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, MIN_CHUNK_SIZE) == (800, 120, 100)
    # chunk_pages() really uses them when called without sizes
    text = " ".join(f"Sentence number {n:04d} has some words in it." for n in range(60))
    assert chunk_pages([page(text)]) == chunk_pages([page(text)], 800, 120)
    assert max(len(c.text) for c in chunk_pages([page(text)])) <= 800
    assert len(chunk_pages([page(text)])) > 1


@pytest.mark.parametrize("size", [99, 50, 1, 0, -5])
def test_chunk_size_below_minimum_is_rejected(size):
    with pytest.raises(ValueError, match="chunk_size must be at least 100"):
        chunk_pages([page("text")], size, 0)


def test_minimum_chunk_size_is_accepted():
    assert chunk_pages([page("text")], 100, 99)[0].text == "text"


@pytest.mark.parametrize("overlap", [-1, -120])
def test_negative_overlap_is_rejected(overlap):
    with pytest.raises(ValueError, match="overlap must not be negative"):
        chunk_pages([page("text")], 800, overlap)


@pytest.mark.parametrize("size, overlap", [(200, 200), (200, 201), (800, 5000), (100, 100)])
def test_overlap_not_smaller_than_chunk_size_is_rejected(size, overlap):
    with pytest.raises(ValueError, match="must be smaller than chunk_size"):
        chunk_pages([page("text")], size, overlap)


@pytest.mark.parametrize("bad", [800.0, "800", None, True, [800]])
def test_non_integer_chunk_size_is_rejected(bad):
    with pytest.raises(TypeError, match="chunk_size must be an integer"):
        chunk_pages([page("text")], bad, 0)


@pytest.mark.parametrize("bad", [10.5, "10", None, False])
def test_non_integer_overlap_is_rejected(bad):
    with pytest.raises(TypeError, match="overlap must be an integer"):
        chunk_pages([page("text")], 800, bad)


def test_settings_are_validated_even_when_there_are_no_pages():
    with pytest.raises(ValueError):
        chunk_pages([], 50, 10)


def test_validate_chunk_settings_accepts_valid_values():
    validate_chunk_settings(100, 0)
    validate_chunk_settings(800, 120)
    validate_chunk_settings(100, 99)


# --------------------------------------------------------------------------
# Empty, blank and short pages
# --------------------------------------------------------------------------


def test_no_pages_gives_no_chunks():
    assert chunk_pages([]) == []


@pytest.mark.parametrize("text", ["", " ", "   \n\n\t  ", "\n", "\r\n\r\n", "\u00a0\u3000 \u2003"])
def test_blank_pages_produce_no_chunks(text):
    assert chunk_pages([page(text)]) == []


def test_blank_page_keeps_the_numbers_of_the_other_pages():
    chunks = chunk_pages([page("First page.", 1), page("", 2), page("Third page.", 3)])

    assert [(c.page_number, c.chunk_id) for c in chunks] == [
        (1, "policy.pdf:1:0"),
        (3, "policy.pdf:3:0"),
    ]


def test_short_page_is_one_chunk_with_the_original_text():
    chunks = chunk_pages([page("Casual leave: 12 days per year.", 3)])

    assert chunks == [
        Chunk(
            chunk_id="policy.pdf:3:0",
            file_name="policy.pdf",
            page_number=3,
            chunk_index=0,
            text="Casual leave: 12 days per year.",
        )
    ]


def test_text_exactly_chunk_size_is_one_chunk_and_one_more_character_makes_two():
    exact = ("word " * 19) + "words"  # 100 chars
    assert len(exact) == 100
    assert chunk_texts(exact, 100, 0) == [exact]
    assert chunk_texts(exact + "s", 100, 0) == [("word " * 19).strip(), "wordss"]


def test_page_shorter_than_overlap_is_one_chunk_without_duplication():
    assert chunk_texts("Hello world.", 200, 150) == ["Hello world."]


# --------------------------------------------------------------------------
# Whitespace handling
# --------------------------------------------------------------------------


def test_runs_of_spaces_tabs_and_single_line_breaks_become_one_space():
    text = "Leave   is\ttaken\nin   days,\r\nnot hours.\u00a0Really."

    assert chunk_texts(text) == ["Leave is taken in days, not hours. Really."]


def test_blank_line_is_a_paragraph_break_and_is_kept():
    text = "Heading\n\nFirst paragraph\ncontinues here.\n  \n\n\nSecond paragraph."

    assert chunk_texts(text) == ["Heading\n\nFirst paragraph continues here.\n\nSecond paragraph."]


def test_chunks_never_start_or_end_with_whitespace():
    text = "  \n  " + sentences(1, 30) + "\n\n  " + sentences(31, 40) + "  \n"
    for overlap in (0, 30, 60):
        for text_ in chunk_texts(text, 100, overlap):
            assert text_ == text_.strip() and text_


# --------------------------------------------------------------------------
# Boundaries: paragraph, then sentence, then word
# --------------------------------------------------------------------------


def test_paragraphs_that_fit_are_never_split():
    paragraphs = [f"Paragraph {n} " + "x" * 55 for n in range(5)]  # 66 chars each
    chunks = chunk_texts("\n\n".join(paragraphs), 100, 0)

    assert chunks == paragraphs  # one paragraph per chunk, none cut


def test_whole_paragraphs_are_packed_together_up_to_the_limit():
    paragraphs = ["A" * 40, "B" * 40, "C" * 40, "D" * 40]
    chunks = chunk_texts("\n\n".join(paragraphs), 100, 0)

    assert chunks == ["A" * 40 + "\n\n" + "B" * 40, "C" * 40 + "\n\n" + "D" * 40]


def test_a_paragraph_that_does_not_fit_starts_a_new_chunk():
    chunks = chunk_texts("A" * 60 + "\n\n" + "B" * 60, 100, 0)

    assert chunks == ["A" * 60, "B" * 60]


def test_a_paragraph_exactly_as_long_as_the_limit_is_kept_whole():
    exact = "a" * 49 + "." + " " + "b" * 48 + "."  # two sentences, 100 chars in total
    assert len(exact) == 100

    assert chunk_texts("B" * 30 + "\n\n" + exact, 100, 0) == ["B" * 30, exact]


def test_a_sentence_exactly_as_long_as_the_limit_is_kept_whole():
    exact = "a" * 49 + " " + "b" * 50  # no punctuation, 100 chars
    assert len(exact) == 100

    assert chunk_texts("Intro. " + exact, 100, 0) == ["Intro.", exact]


def test_short_heading_stays_with_the_start_of_its_long_paragraph():
    body = sentences(1, 12)  # 12 * 21 + 11 = 263 chars, longer than the limit
    chunks = chunk_texts("Leave policy\n\n" + body, 100, 0)

    assert chunks[0].startswith("Leave policy\n\nSentence 001 is here.")


def test_long_paragraph_is_cut_only_between_sentences():
    chunks = chunk_texts(sentences(1, 20), 100, 0)

    assert len(chunks) == 5
    for c in chunks:
        assert re.fullmatch(r"(Sentence \d{3} is here\.)( Sentence \d{3} is here\.)*", c)
    assert " ".join(chunks) == sentences(1, 20)


@pytest.mark.parametrize(
    "ending",
    [".", "!", "?", "\u06d4", "\u061f"],  # . ! ? and the Urdu/Arabic full stop and question mark
    ids=["period", "exclamation", "question", "urdu-full-stop", "arabic-question"],
)
def test_all_sentence_end_marks_are_boundaries(ending):
    sentence = "word " * 8 + "end" + ending  # 44 chars
    chunks = chunk_texts(" ".join([sentence] * 6), 100, 0)

    assert len(chunks) == 3
    assert all(c == f"{sentence} {sentence}" for c in chunks)


def test_decimal_numbers_and_inline_dots_are_not_sentence_ends():
    # no whitespace after the dots, so "3.50" and "a.b" stay in one piece
    text = ("Fee is Rs 3.50 per day see a.b for more. " * 6).strip()
    for c in chunk_texts(text, 100, 0):
        assert "3.50" in c or "3." not in c
        assert "a.b" in c or "a." not in c


def test_cjk_sentences_are_cut_after_the_ideographic_full_stop_without_spaces():
    sentence = "这是一个很短的测试句子。"  # 12 chars, no spaces anywhere
    chunks = chunk_texts(sentence * 30, 100, 0)  # 360 chars

    assert all(c.endswith("。") for c in chunks)
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == sentence * 30


def test_over_long_sentence_is_cut_between_words():
    words = [f"w{n:03d}" for n in range(1, 61)]  # 60 words of 4 chars, no punctuation
    chunks = chunk_texts(" ".join(words), 100, 0)

    assert len(chunks) == 3
    assert all(len(c) <= 100 for c in chunks)
    assert " ".join(chunks) == " ".join(words)  # nothing cut inside a word


def test_a_word_is_never_cut_when_it_fits_in_a_chunk():
    text = " ".join(["unbelievably"] * 40)  # 12-char words
    for c in chunk_texts(text, 100, 30):
        assert set(c.split()) == {"unbelievably"}


# --------------------------------------------------------------------------
# Overlap
# --------------------------------------------------------------------------


def test_zero_overlap_chunks_do_not_repeat_text():
    chunks = chunk_texts(sentences(1, 20), 100, 0)

    assert chunks == [sentences(4 * i + 1, 4 * i + 4) for i in range(5)]
    assert " ".join(chunks) == sentences(1, 20)


def test_overlap_repeats_the_last_whole_sentences_of_the_previous_chunk():
    # size 100 holds 4 sentences (87 chars). Overlap 50 holds 2 (43 chars, 3 would be 65).
    chunks = chunk_texts(sentences(1, 20), 100, 50)

    assert chunks == [sentences(2 * i + 1, 2 * i + 4) for i in range(9)]


def test_overlap_is_sentence_aligned_and_never_longer_than_allowed():
    overlap = 50
    chunks = chunk_texts(sentences(1, 20), 100, overlap)

    for previous, following in pairwise(chunks):
        shared = max(k for k in range(len(following) + 1) if previous.endswith(following[:k]))
        assert 0 < shared <= overlap
        assert following.startswith("Sentence ")


def test_overlap_of_a_single_sentence_when_two_do_not_fit():
    # overlap 30 fits one 21-char sentence but not two (43)
    chunks = chunk_texts(sentences(1, 20), 100, 30)

    assert chunks[0] == sentences(1, 4)
    assert chunks[1] == sentences(4, 7)


def test_overlap_falls_back_to_whole_words_inside_a_long_sentence():
    words = [f"w{n:03d}" for n in range(1, 61)]
    chunks = chunk_texts(" ".join(words), 100, 30)  # 6 words = 29 chars fit, 7 do not

    assert len(chunks) > 3
    for previous, following in pairwise(chunks):
        assert following.split()[:6] == previous.split()[-6:]
    assert all(len(c) <= 100 for c in chunks)


def test_overlap_uses_the_last_words_when_the_last_sentence_is_longer_than_the_overlap():
    first = "The quick brown fox jumps over the lazy dog today."  # 50 chars
    second = "Pack my box with five dozen liquor jugs right now."  # 50 chars
    assert len(first) == len(second) == 50

    chunks = chunk_texts(first + " " + second, 100, 20)

    assert chunks == [first, "the lazy dog today. " + second]


def test_overlap_is_shortened_so_the_next_sentence_still_fits():
    first = ("one " * 9) + "end."  # 40 chars
    second = "w" * 94 + "."  # 95 chars: only 4 characters are left for the overlap
    chunks = chunk_texts(first + " " + second, 100, 90)

    assert chunks == [first, "end. " + second]
    assert len(chunks[1]) == 100


def test_no_overlap_is_possible_when_the_next_sentence_fills_the_chunk():
    first = ("one " * 9) + "end."
    second = "w" * 99 + "."  # exactly 100 chars
    chunks = chunk_texts(first + " " + second, 100, 90)

    assert chunks == [first, second]


def test_no_overlap_when_the_last_word_is_longer_than_the_overlap():
    first = "alpha beta " + "g" * 60 + "."  # last (only) word of the final part is 61 chars
    second = "z" * 60 + "."
    chunks = chunk_texts(first + " " + second, 100, 20)

    assert chunks == [first, second]


def test_pieces_of_a_split_long_word_are_not_repeated_as_overlap():
    # The 100-character pieces are longer than the overlap, so nothing is carried over
    # (a half word would be a useless start for the next chunk).
    assert chunk_texts("y" * 250, 100, 60) == ["y" * 100, "y" * 100, "y" * 50]


def test_all_text_is_kept_when_overlap_is_used():
    text = " ".join(f"Sentence {n} about leave, travel or pay." for n in range(1, 60))
    for overlap in (0, 10, 40, 99):
        flattened = [t for c in chunk_texts(text, 100, overlap) for t in c.split()]
        assert is_subsequence(text.split(), flattened)


# --------------------------------------------------------------------------
# Maximum chunk size, empty chunks, long paragraphs
# --------------------------------------------------------------------------


@pytest.mark.parametrize("size, overlap", [(100, 0), (100, 99), (100, 50), (150, 30), (800, 120), (1000, 999)])
def test_no_chunk_is_longer_than_the_limit_or_empty(size, overlap):
    text = ("Leave policy: employees get 12 days. " * 40) + "\n\n" + ("x" * 3 * size) + "\n\n" + sentences(1, 80)
    chunks = chunk_pages([page(text)], size, overlap)

    assert chunks
    assert all(0 < len(c.text) <= size for c in chunks)


def test_very_long_paragraph_gives_many_chunks_within_the_limit():
    text = sentences(1, 500)  # about 11 000 characters in one paragraph
    chunks = chunk_pages([page(text)], 800, 120)

    assert 10 < len(chunks) < 40
    assert all(len(c.text) <= 800 for c in chunks)
    assert all(c.text.startswith("Sentence ") and c.text.endswith("here.") for c in chunks)


# --------------------------------------------------------------------------
# Long words (last resort)
# --------------------------------------------------------------------------


def test_word_longer_than_the_limit_is_cut_into_pieces_of_exactly_the_limit():
    assert chunk_texts("x" * 250, 100, 0) == ["x" * 100, "x" * 100, "x" * 50]


def test_word_exactly_the_size_of_the_limit_is_not_cut_but_one_more_character_is():
    assert chunk_texts("x" * 100, 100, 0) == ["x" * 100]
    assert chunk_texts("x" * 101, 100, 0) == ["x" * 100, "x"]


def test_long_word_between_normal_words_keeps_everything():
    url = "https://example.com/" + "a" * 240
    text = f"See {url} for details."
    chunks = chunk_texts(text, 100, 0)

    assert all(len(c) <= 100 for c in chunks)
    assert no_space("".join(chunks)) == no_space(text)
    assert chunks[0] == "See" and chunks[-1].endswith("for details.")


def test_long_word_pieces_respect_the_limit_with_overlap_too():
    chunks = chunk_texts("Start " + "z" * 333 + " finish", 100, 60)

    assert all(0 < len(c) <= 100 for c in chunks)
    assert chunks[0] == "Start" and chunks[-1].endswith("finish")


def test_long_word_split_never_separates_a_combining_mark_from_its_base():
    word = "x" + "e\u0301" * 80  # marks sit at even positions; the window edge falls on one
    pieces = chunk_texts(word, 100, 0)

    assert "".join(pieces) == word
    assert all(len(p) <= 100 for p in pieces)
    assert all(unicodedata.category(p[0])[0] != "M" for p in pieces)
    assert len(pieces[0]) == 99  # backed off by one so the accent stays with its letter


def test_hindi_long_word_is_not_cut_before_a_matra_or_virama():
    word = "क्षत्रिय" * 40  # 320 chars full of vowel signs and viramas
    pieces = chunk_texts(word, 100, 0)

    assert "".join(pieces) == word
    assert all(len(p) <= 100 for p in pieces)
    assert all(unicodedata.category(p[0])[0] != "M" for p in pieces)


def test_a_window_made_only_of_combining_marks_is_still_cut_at_the_limit():
    word = "\u0301" * 250  # pathological: no base character anywhere
    pieces = chunk_texts(word, 100, 0)

    assert pieces == ["\u0301" * 100, "\u0301" * 100, "\u0301" * 50]


def test_cjk_text_without_any_punctuation_is_cut_at_the_limit():
    text = "汉字" * 120  # 240 characters
    pieces = chunk_texts(text, 100, 0)

    assert [len(p) for p in pieces] == [100, 100, 40]
    assert "".join(pieces) == text


# --------------------------------------------------------------------------
# Unicode
# --------------------------------------------------------------------------


UNICODE_SAMPLES = {
    "urdu": "یہ پالیسی تمام ملازمین پر لاگو ہوتی ہے۔ کیا چھٹیاں ملتی ہیں؟ جی ہاں، سالانہ بارہ دن۔ ",
    "urdu-harakat": "اَللّٰہُ بِکُلِّ شَیْءٍ عَلِیْمٌ۔ سُبْحَانَ رَبِّیَ الْاَعْلٰی۔ ",
    "arabic-tashkeel": "الحَمْدُ لِلّٰهِ رَبِّ العَالَمِينَ. الرَّحْمٰنِ الرَّحِيمِ. ",
    "hindi": "यह नीति सभी कर्मचारियों पर लागू होती है। हिन्दी रिपोर्ट देखें। ",
    "japanese": "これは休暇に関する規則です。年に十二日あります。 ",
    "korean": "이것은 휴가 정책입니다. 연간 12일이 있습니다. ",
    "emoji": "Approved ✅ by HR 👩🏽‍💼 on time. Not approved ❌ today. ",
}


@pytest.mark.parametrize("name", UNICODE_SAMPLES)
def test_unicode_text_is_kept_exactly(name):
    text = (UNICODE_SAMPLES[name] * 12).strip()
    chunks = chunk_texts(text, 100, 0)

    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)
    # no character, mark or word is lost or changed; only spaces between chunks differ
    assert no_space("".join(chunks)) == no_space(text)
    assert " ".join(chunks).split() == text.split()


@pytest.mark.parametrize("name", UNICODE_SAMPLES)
def test_unicode_text_with_overlap_loses_nothing(name):
    text = (UNICODE_SAMPLES[name] * 12).strip()
    flattened = [t for c in chunk_texts(text, 100, 40) for t in c.split()]

    assert is_subsequence(text.split(), flattened)


def test_text_is_not_unicode_normalised():
    decomposed = "Cafe\u0301 and caf\u00e9"  # NFD é and NFC é must stay as they are
    assert chunk_texts(decomposed) == [decomposed]


def test_unicode_file_names_are_used_unchanged_in_ids():
    chunks = chunk_pages([page("متن", 2, "रिपोर्ट.pdf")])

    assert chunks[0].chunk_id == "रिपोर्ट.pdf:2:0"
    assert chunks[0].file_name == "रिपोर्ट.pdf"


# --------------------------------------------------------------------------
# IDs, indexes and metadata
# --------------------------------------------------------------------------


def test_chunk_id_format_is_file_page_index():
    chunks = chunk_pages([page(sentences(1, 20), 3)], 100, 0)

    assert [c.chunk_id for c in chunks] == [f"policy.pdf:3:{i}" for i in range(5)]


def test_chunk_index_restarts_at_zero_on_every_page():
    pages = [page(sentences(1, 20), 1), page(sentences(1, 8), 2), page(sentences(1, 20), 3)]
    chunks = chunk_pages(pages, 100, 0)

    by_page: dict[int, list[int]] = {}
    for c in chunks:
        by_page.setdefault(c.page_number, []).append(c.chunk_index)
    assert by_page == {1: [0, 1, 2, 3, 4], 2: [0, 1], 3: [0, 1, 2, 3, 4]}


def test_ids_are_stable_between_runs_and_unique_within_a_run():
    pages = [page(sentences(1, 40), n, name) for name in ("a.pdf", "b.pdf") for n in (1, 2, 3)]

    first = chunk_pages(pages, 100, 30)
    second = chunk_pages(list(pages), 100, 30)

    assert first == second
    ids = [c.chunk_id for c in first]
    assert len(ids) == len(set(ids))


def test_same_page_number_in_two_files_gives_different_ids():
    chunks = chunk_pages([page("text", 1, "a.pdf"), page("text", 1, "b.pdf")])

    assert [c.chunk_id for c in chunks] == ["a.pdf:1:0", "b.pdf:1:0"]


def test_ids_stay_unique_and_decodable_even_for_names_that_contain_a_colon():
    # Sanitised upload names never contain ":", but the ID is still unambiguous:
    # the page and the index are the last two fields.
    pages = [page(sentences(1, 12), 1, "a"), page(sentences(1, 12), 1, "a:1"), page(sentences(1, 12), 11, "a")]
    chunks = chunk_pages(pages, 100, 0)

    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    for c in chunks:
        name, number, index = c.chunk_id.rsplit(":", 2)
        assert (name, int(number), int(index)) == (c.file_name, c.page_number, c.chunk_index)


def test_every_chunk_keeps_the_file_name_and_page_number_of_its_page():
    pages = [page(sentences(1, 15), 2, "hr.pdf"), page(sentences(1, 15), 7, "travel.pdf")]
    chunks = chunk_pages(pages, 100, 20)

    assert {(c.file_name, c.page_number) for c in chunks} == {("hr.pdf", 2), ("travel.pdf", 7)}
    for c in chunks:
        assert c.chunk_id == f"{c.file_name}:{c.page_number}:{c.chunk_index}"


def test_output_follows_the_input_order_of_pages():
    chunks = chunk_pages([page("third", 3), page("first", 1), page("second", 2)])

    assert [c.page_number for c in chunks] == [3, 1, 2]


def test_duplicate_file_and_page_in_the_input_is_rejected():
    with pytest.raises(ValueError, match="duplicate page"):
        chunk_pages([page("one", 1), page("two", 1)])


def test_pages_may_come_from_any_iterable():
    chunks = chunk_pages(page(f"page {n}", n) for n in range(1, 4))

    assert [c.page_number for c in chunks] == [1, 2, 3]


def test_chunk_is_a_frozen_dataclass():
    c = chunk_pages([page("text")])[0]
    with pytest.raises(AttributeError):
        c.text = "changed"  # type: ignore[misc]


# --------------------------------------------------------------------------
# Pages are never mixed
# --------------------------------------------------------------------------


def test_a_chunk_never_contains_text_from_two_pages():
    pages = [page(" ".join(f"P{n}-word{i}" for i in range(80)), n) for n in range(1, 6)]
    chunks = chunk_pages(pages, 100, 40)

    for c in chunks:
        assert set(re.findall(r"P(\d+)-", c.text)) == {str(c.page_number)}


def test_a_sentence_running_over_a_page_break_is_not_joined():
    first = page("The travel allowance for domestic trips is", 3)
    second = page("Rs 3,000 per day.", 4)
    chunks = chunk_pages([first, second], 800, 120)

    assert [(c.page_number, c.text) for c in chunks] == [
        (3, "The travel allowance for domestic trips is"),
        (4, "Rs 3,000 per day."),
    ]


def test_a_page_is_chunked_the_same_way_alone_or_together_with_other_pages():
    target = page(sentences(1, 30), 2)
    alone = chunk_pages([target], 100, 40)
    together = chunk_pages([page(sentences(1, 25), 1), target, page(sentences(1, 25), 3)], 100, 40)

    assert [c for c in together if c.page_number == 2] == alone


# --------------------------------------------------------------------------
# The input is not modified
# --------------------------------------------------------------------------


def test_input_list_and_pages_are_not_modified():
    pages = [page("  " + sentences(1, 20) + "  ", 1), page("", 2), page("A\n\nB", 3)]
    snapshot = [(p.file_name, p.page_number, p.text) for p in pages]
    originals = list(pages)

    chunk_pages(pages, 100, 20)

    assert pages == originals
    assert all(a is b for a, b in zip(pages, originals, strict=True))
    assert [(p.file_name, p.page_number, p.text) for p in pages] == snapshot


def test_mutable_page_like_objects_are_not_changed():
    obj = SimpleNamespace(file_name="x.pdf", page_number=1, text=sentences(1, 10))
    before = dict(vars(obj))

    chunk_pages([obj], 100, 20)

    assert vars(obj) == before


# --------------------------------------------------------------------------
# Randomised invariants (fixed seeds, so the test is deterministic)
# --------------------------------------------------------------------------


_VOCAB = ["leave", "days", "travel", "Rs", "3,000", "policy", "HR-204", "approval", "ہفتہ", "रिपोर्ट", "会议", "ok"]


def _random_text(rng: random.Random, long_words: bool, size: int) -> str:
    parts: list[str] = []
    for _ in range(rng.randint(0, 120)):
        word = rng.choice(_VOCAB)
        if long_words and rng.random() < 0.05:
            word = "L" * rng.randint(size + 1, 3 * size)
        parts.append(word)
        roll = rng.random()
        if roll < 0.12:
            parts[-1] += rng.choice([".", "!", "?", "۔", "؟"])
        parts.append(rng.choice([" ", " ", " ", "  ", "\n", "\n\n", " \n \n", "\t"]) if roll < 0.9 else " ")
    return "".join(parts)


@pytest.mark.parametrize("seed", range(40))
def test_random_pages_respect_every_invariant(seed):
    rng = random.Random(seed)
    size = rng.choice([100, 120, 250, 800])
    overlap = rng.choice([0, 1, 30, size // 2, size - 1])
    text = _random_text(rng, long_words=False, size=size)

    chunks = chunk_pages([page(text, 5)], size, overlap)

    if not text.strip():
        assert chunks == []
        return
    assert chunks
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(c.page_number == 5 and c.file_name == "policy.pdf" for c in chunks)
    assert all(0 < len(c.text) <= size and c.text == c.text.strip() for c in chunks)
    flattened = [t for c in chunks for t in c.text.split()]
    assert is_subsequence(text.split(), flattened)  # nothing lost, order kept
    assert chunks == chunk_pages([page(text, 5)], size, overlap)  # deterministic


@pytest.mark.parametrize("seed", range(40))
def test_random_pages_with_long_words_lose_no_characters_without_overlap(seed):
    rng = random.Random(1000 + seed)
    size = rng.choice([100, 120, 250])
    text = _random_text(rng, long_words=True, size=size)

    chunks = chunk_pages([page(text)], size, 0)

    assert all(0 < len(c.text) <= size for c in chunks)
    assert no_space("".join(c.text for c in chunks)) == no_space(text)


@pytest.mark.parametrize("seed", range(20))
def test_random_pages_with_long_words_and_overlap_keep_the_limits(seed):
    rng = random.Random(2000 + seed)
    size = rng.choice([100, 120, 250])
    text = _random_text(rng, long_words=True, size=size)

    chunks = chunk_pages([page(text)], size, size - 1)

    assert all(0 < len(c.text) <= size for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


# --------------------------------------------------------------------------
# End to end: generated PDF -> extract_pages() -> chunk_pages()
# --------------------------------------------------------------------------


def test_chunking_works_on_pages_extracted_from_a_real_pdf(tmp_path):
    long_text = " ".join(f"Rule {n:02d} says that leave must be approved in advance." for n in range(1, 41))
    doc = pymupdf.open()
    first = doc.new_page()
    first.insert_textbox(pymupdf.Rect(40, 40, 560, 780), long_text, fontsize=9)
    doc.new_page()  # page 2 stays blank
    third = doc.new_page()
    third.insert_textbox(pymupdf.Rect(40, 40, 560, 780), "Office timings: 9 AM to 5 PM.", fontsize=11)
    path = tmp_path / "policy.pdf"
    doc.save(path)

    pages = extract_pages(path, "policy.pdf")
    chunks = chunk_pages(pages, 200, 40)

    assert [p.page_number for p in pages] == [1, 2, 3] and pages[1].text == ""
    assert {c.page_number for c in chunks} == {1, 3}
    assert [c.chunk_id for c in chunks if c.page_number == 3] == ["policy.pdf:3:0"]
    assert [c.chunk_id for c in chunks if c.page_number == 1][:3] == [
        "policy.pdf:1:0",
        "policy.pdf:1:1",
        "policy.pdf:1:2",
    ]
    assert all(0 < len(c.text) <= 200 for c in chunks)
    assert is_subsequence(pages[0].text.split(), [t for c in chunks if c.page_number == 1 for t in c.text.split()])
    assert chunks[-1].text == "Office timings: 9 AM to 5 PM."


def test_token_aware_chunking_strictly_respects_token_limit():
    # Dense text: 50 words that would normally be ~350 characters
    words = [f"word{i}" for i in range(50)]
    text = " ".join(words)
    counter = lambda s: len(s.split()) + 2  # word count + 2 special tokens

    # Chunk with max_tokens=10 (at most 8 words per chunk)
    chunks = chunk_pages([page(text)], chunk_size=800, overlap=50, max_tokens=10, token_counter=counter)

    assert len(chunks) > 1
    for c in chunks:
        assert counter(c.text) <= 10
        assert len(c.text) <= 800
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert [c.chunk_id for c in chunks] == [f"policy.pdf:1:{i}" for i in range(len(chunks))]


def test_token_aware_chunking_handles_very_long_dense_word():
    # Single 120-character word with a tight token budget
    long_word = "a" * 120
    counter = lambda s: len(s) // 5 + 1
    chunks = chunk_pages([page(long_word)], chunk_size=200, overlap=20, max_tokens=10, token_counter=counter)

    assert len(chunks) >= 2
    for c in chunks:
        assert counter(c.text) <= 10
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))


def test_module_has_no_embedding_or_vector_store_dependency():
    # Stage 2 scope: only the standard library (the PageText import is type-only).
    text = Path(chunker.__file__).read_text(encoding="utf-8")
    for forbidden in ("sentence_transformers", "chromadb", "pymupdf", "fastapi"):
        assert forbidden not in text
