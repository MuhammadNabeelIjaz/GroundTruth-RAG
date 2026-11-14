import hashlib
import threading
import time
import unicodedata

import pytest
from fastapi.testclient import TestClient

from backend.api import documents
from backend.api.documents import sanitize_filename
from backend.config import settings
from backend.main import app


def upload(client, *files):
    """files: (file_name, content) pairs -> POST /documents."""
    return client.post(
        "/documents",
        files=[("files", (name, content, "application/pdf")) for name, content in files],
    )


def files_in(uploads_dir):
    """Everything in the uploads folder, including leftover temporary files."""
    return sorted(p.name for p in uploads_dir.iterdir()) if uploads_dir.exists() else []


# --- successful uploads ------------------------------------------------------


def test_valid_pdf_is_saved_and_pages_are_reported(
    client, isolated_uploads_dir, make_pdf
):
    content = make_pdf(["alpha page one", "bravo page two", "charlie page three"])

    response = upload(client, ("guide.pdf", content))

    assert response.status_code == 200
    [result] = response.json()["results"]
    assert result["success"] is True
    assert result["file_name"] == "guide.pdf"
    assert result["original_name"] == "guide.pdf"
    assert result["page_count"] == 3
    assert result["blank_pages"] == []
    assert [p["page_number"] for p in result["pages"]] == [1, 2, 3]
    assert result["pages"][1]["preview"].startswith("bravo")
    assert result["pages"][0]["char_count"] == len("alpha page one")
    assert (isolated_uploads_dir / "guide.pdf").read_bytes() == content
    assert files_in(isolated_uploads_dir) == ["guide.pdf"]  # no temp file left


def test_blank_pages_are_reported_and_the_pdf_is_accepted(
    client, isolated_uploads_dir, make_pdf
):
    response = upload(client, ("gaps.pdf", make_pdf(["one", None, "three"])))

    assert response.status_code == 200
    [result] = response.json()["results"]
    assert result["page_count"] == 3
    assert result["blank_pages"] == [2]
    assert result["pages"][1]["char_count"] == 0
    assert result["pages"][2]["page_number"] == 3


def test_preview_is_short_and_whitespace_is_collapsed(client, make_pdf):
    long_text = "word " * 100
    response = upload(client, ("long.pdf", make_pdf([long_text])))

    preview = response.json()["results"][0]["pages"][0]["preview"]

    assert len(preview) <= documents.PREVIEW_CHARS
    assert "  " not in preview


def test_multiple_valid_pdfs_in_one_request(client, isolated_uploads_dir, make_pdf):
    response = upload(
        client,
        ("policy.pdf", make_pdf(["policy text"])),
        ("handbook.pdf", make_pdf(["handbook one", "handbook two"])),
    )

    assert response.status_code == 200
    first, second = response.json()["results"]
    assert (first["file_name"], first["page_count"]) == ("policy.pdf", 1)
    assert (second["file_name"], second["page_count"]) == ("handbook.pdf", 2)
    assert files_in(isolated_uploads_dir) == ["handbook.pdf", "policy.pdf"]


def test_one_invalid_and_one_valid_pdf_in_the_same_request(
    client, isolated_uploads_dir, make_pdf
):
    response = upload(
        client,
        ("notes.pdf", b"plain text pretending to be a pdf"),
        ("good.pdf", make_pdf(["good content"])),
    )

    assert response.status_code == 200  # at least one file was accepted
    bad, good = response.json()["results"]
    assert bad["success"] is False and bad["status_code"] == 415
    assert good["success"] is True and good["page_count"] == 1
    assert files_in(isolated_uploads_dir) == ["good.pdf"]


def test_valid_file_after_an_invalid_one_is_not_blocked_by_order(
    client, isolated_uploads_dir, make_pdf
):
    response = upload(
        client,
        ("good.pdf", make_pdf(["good content"])),
        ("empty.pdf", b""),
    )

    good, empty = response.json()["results"]
    assert good["success"] is True
    assert empty["status_code"] == 400
    assert files_in(isolated_uploads_dir) == ["good.pdf"]


# --- rejected uploads --------------------------------------------------------


def test_image_only_pdf_is_rejected_with_422(
    client, isolated_uploads_dir, make_image_only_pdf
):
    response = upload(client, ("scan.pdf", make_image_only_pdf()))

    assert response.status_code == 422
    [result] = response.json()["results"]
    assert result["success"] is False and "OCR" in result["error"]
    assert files_in(isolated_uploads_dir) == []


def test_encrypted_pdf_is_rejected_with_400(
    client, isolated_uploads_dir, make_encrypted_pdf
):
    response = upload(client, ("locked.pdf", make_encrypted_pdf()))

    assert response.status_code == 400
    assert "password" in response.json()["results"][0]["error"]
    assert files_in(isolated_uploads_dir) == []


def test_corrupt_pdf_is_rejected_with_400(client, isolated_uploads_dir):
    response = upload(client, ("broken.pdf", b"%PDF-1.4\nnot a real pdf body\n"))

    assert response.status_code == 400
    assert files_in(isolated_uploads_dir) == []


def test_text_file_renamed_to_pdf_is_rejected_with_415(client, isolated_uploads_dir):
    response = upload(client, ("notes.pdf", b"hello, this is only text\n"))

    assert response.status_code == 415
    assert "%PDF-" in response.json()["results"][0]["error"]
    assert files_in(isolated_uploads_dir) == []


def test_real_pdf_with_wrong_extension_is_rejected_with_415(
    client, isolated_uploads_dir, make_pdf
):
    response = upload(client, ("guide.txt", make_pdf(["text"])))

    assert response.status_code == 415
    assert files_in(isolated_uploads_dir) == []


def test_empty_file_is_rejected_with_400(client, isolated_uploads_dir):
    response = upload(client, ("empty.pdf", b""))

    assert response.status_code == 400
    assert files_in(isolated_uploads_dir) == []


def test_oversized_upload_is_rejected_with_413(
    client, isolated_uploads_dir, monkeypatch
):
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    too_big = b"%PDF-" + b"0" * (1024 * 1024 + 10)

    response = upload(client, ("big.pdf", too_big))

    assert response.status_code == 413
    assert "1 MB" in response.json()["results"][0]["error"]
    assert files_in(isolated_uploads_dir) == []


def test_file_exactly_at_the_limit_is_not_rejected_for_size(
    client, monkeypatch, make_pdf
):
    content = make_pdf(["fits"])
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    padded = content + b"\n" * (1024 * 1024 - len(content))  # exactly 1 MiB

    response = upload(client, ("exact.pdf", padded))

    assert response.status_code == 200


def test_unexpected_error_is_reported_for_that_file_and_cleans_up(
    client, isolated_uploads_dir, make_pdf, monkeypatch
):
    def explode(path, file_name):
        raise RuntimeError("boom")

    monkeypatch.setattr(documents, "extract_pages", explode)

    response = upload(client, ("guide.pdf", make_pdf(["text"])))

    assert response.status_code == 500
    assert "boom" not in response.text  # internal details are not leaked
    assert files_in(isolated_uploads_dir) == []


def test_request_without_files_is_rejected(client):
    response = client.post("/documents")

    assert response.status_code == 422


def test_when_every_file_fails_the_first_failure_sets_the_status(
    client, isolated_uploads_dir
):
    response = upload(
        client,
        ("empty.pdf", b""),  # 400
        ("notes.pdf", b"text only"),  # 415
    )

    assert response.status_code == 400
    assert [r["status_code"] for r in response.json()["results"]] == [400, 415]
    assert files_in(isolated_uploads_dir) == []


# --- duplicates ----------------------------------------------------------------


def test_duplicate_name_returns_409_and_keeps_the_original(
    client, isolated_uploads_dir, make_pdf
):
    original = make_pdf(["the original document"])
    assert upload(client, ("guide.pdf", original)).status_code == 200
    digest = hashlib.sha256((isolated_uploads_dir / "guide.pdf").read_bytes()).hexdigest()

    response = upload(client, ("guide.pdf", make_pdf(["a different document"])))

    assert response.status_code == 409
    assert response.json()["results"][0]["success"] is False
    saved = (isolated_uploads_dir / "guide.pdf").read_bytes()
    assert hashlib.sha256(saved).hexdigest() == digest  # untouched
    assert files_in(isolated_uploads_dir) == ["guide.pdf"]


def test_duplicate_name_differing_only_in_case_is_also_a_conflict(
    client, isolated_uploads_dir, make_pdf
):
    upload(client, ("Guide.pdf", make_pdf(["first"])))

    response = upload(client, ("guide.PDF", make_pdf(["second"])))

    assert response.status_code == 409
    assert files_in(isolated_uploads_dir) == ["Guide.pdf"]


def test_same_name_twice_in_one_request_accepts_the_first_only(
    client, isolated_uploads_dir, make_pdf
):
    response = upload(
        client,
        ("same.pdf", make_pdf(["first copy"])),
        ("same.pdf", make_pdf(["second copy"])),
    )

    first, second = response.json()["results"]
    assert first["success"] is True
    assert second["status_code"] == 409
    assert files_in(isolated_uploads_dir) == ["same.pdf"]


# --- file names ----------------------------------------------------------------


@pytest.mark.parametrize(
    "raw_name",
    ["../../evil.pdf", "..\\..\\evil.pdf", "/etc/evil.pdf", "C:\\temp\\evil.pdf"],
)
def test_path_traversal_names_are_reduced_to_a_safe_base_name(
    client, tmp_path, isolated_uploads_dir, make_pdf, raw_name
):
    response = upload(client, (raw_name, make_pdf(["text"])))

    assert response.status_code == 200
    [result] = response.json()["results"]
    assert result["file_name"] == "evil.pdf"
    # original_name is what the server received; the multipart parser itself may
    # already have dropped a Windows drive path such as C:\temp\.
    assert result["original_name"].endswith("evil.pdf")
    assert files_in(isolated_uploads_dir) == ["evil.pdf"]
    assert not (tmp_path / "evil.pdf").exists()  # nothing written outside uploads
    assert not (tmp_path.parent / "evil.pdf").exists()


@pytest.mark.parametrize(
    "raw_name, expected",
    [
        ("report.pdf", "report.pdf"),
        ("Annual Report 2024.pdf", "Annual Report 2024.pdf"),
        ("a<b>:c?.pdf", "a_b__c_.pdf"),
        ("CON.pdf", "_CON.pdf"),
        ("con.txt.pdf", "_con.txt.pdf"),
        ("...", ""),
        ("..", ""),
        ("", ""),
        ("  spaced.pdf  ", "spaced.pdf"),
    ],
)
def test_sanitize_filename(raw_name, expected):
    assert sanitize_filename(raw_name) == expected


def test_very_long_names_are_shortened_but_keep_the_extension():
    name = sanitize_filename("x" * 500 + ".pdf")

    assert len(name) == documents.MAX_NAME_LENGTH
    assert name.endswith(".pdf")


def test_name_with_no_usable_characters_is_rejected(client, isolated_uploads_dir, make_pdf):
    response = upload(client, ("..", make_pdf(["text"])))

    assert response.status_code == 400
    assert files_in(isolated_uploads_dir) == []


# --- Unicode file names (R2) ---------------------------------------------------

HINDI = "हिन्दी रिपोर्ट.pdf"  # contains combining vowel signs and a virama
URDU = "رپورٹ.pdf"  # plain Urdu, no diacritics
ARABIC_DIACRITICS = "اَلْعَرَبِيَّة.pdf"  # fatha, sukun, shadda ...
JAPANESE = "日本語のファイル.pdf"
KOREAN = "한국어 문서.pdf"


@pytest.mark.parametrize(
    "name", [HINDI, URDU, ARABIC_DIACRITICS, JAPANESE, KOREAN, "Café 2024.pdf"]
)
def test_names_in_any_script_are_kept_unchanged(name):
    assert sanitize_filename(name) == name


@pytest.mark.parametrize(
    "name", [HINDI, URDU, ARABIC_DIACRITICS, JAPANESE, KOREAN, "Café.pdf"]
)
def test_non_latin_names_are_stored_and_reported_unchanged(
    client, isolated_uploads_dir, make_pdf, name
):
    response = upload(client, (name, make_pdf(["text"])))

    assert response.status_code == 200
    [result] = response.json()["results"]
    assert result["file_name"] == name
    assert files_in(isolated_uploads_dir) == [name]


def test_decomposed_and_composed_accents_become_the_same_name():
    decomposed = "Cafe\u0301.pdf"  # "e" followed by a combining acute accent
    composed = "Caf\u00e9.pdf"  # the single character e-acute

    assert decomposed != composed
    assert sanitize_filename(decomposed) == sanitize_filename(composed)
    assert unicodedata.is_normalized("NFC", sanitize_filename(decomposed))


def test_composed_and_decomposed_names_conflict_instead_of_coexisting(
    client, isolated_uploads_dir, make_pdf
):
    assert upload(client, ("Caf\u00e9.pdf", make_pdf(["first"]))).status_code == 200

    response = upload(client, ("Cafe\u0301.pdf", make_pdf(["second"])))

    assert response.status_code == 409
    assert files_in(isolated_uploads_dir) == ["Caf\u00e9.pdf"]


def test_different_hindi_names_do_not_collide(client, isolated_uploads_dir, make_pdf):
    # Before the fix, combining marks became "_" and these two names could
    # turn into look-alikes and produce a false 409.
    first = upload(client, ("हिन्दी.pdf", make_pdf(["a"])))
    second = upload(client, ("हिंदी.pdf", make_pdf(["b"])))

    assert first.status_code == 200 and second.status_code == 200
    assert len(files_in(isolated_uploads_dir)) == 2


@pytest.mark.parametrize(
    "raw_name, expected",
    [
        ("a*b|c\"d.pdf", "a_b_c_d.pdf"),
        ("a\u202eb.pdf", "a_b.pdf"),  # right-to-left override
        ("a\x00b\x1fc.pdf", "a_b_c.pdf"),  # NUL and control characters
        ("a\nb.pdf", "a_b.pdf"),
        ("evil.pdf:stream", "evil.pdf_stream"),
        ("../../" + HINDI, HINDI),  # traversal is removed, script is kept
        ("C:\\temp\\" + URDU, URDU),
        ("CON", "_CON"),
        ("नाम\\..\\x.pdf", "x.pdf"),
    ],
)
def test_unsafe_characters_are_replaced_but_letters_survive(raw_name, expected):
    assert sanitize_filename(raw_name) == expected


def test_long_non_latin_name_fits_the_file_system_limit(
    client, isolated_uploads_dir, make_pdf
):
    # 100 Hindi letters would be about 290 bytes, more than the 255-byte limit
    # of common file systems; the name must be cut by bytes as well.
    raw_name = "ह" * 150 + ".pdf"

    safe_name = sanitize_filename(raw_name)
    assert len(safe_name.encode("utf-8")) <= documents.MAX_NAME_BYTES
    assert safe_name.endswith(".pdf")

    response = upload(client, (raw_name, make_pdf(["text"])))

    assert response.status_code == 200  # no "file name too long" error
    assert files_in(isolated_uploads_dir) == [safe_name]


# --- names without an extension, header limit (R4) -------------------------------


def test_name_without_an_extension_is_kept_and_then_rejected_as_not_pdf(
    client, isolated_uploads_dir, make_pdf
):
    assert sanitize_filename("noext") == "noext"

    response = upload(client, ("noext", make_pdf(["text"])))

    assert response.status_code == 415
    assert response.json()["results"][0]["file_name"] == "noext"
    assert files_in(isolated_uploads_dir) == []


def test_pdf_with_junk_bytes_before_the_header_is_rejected(
    client, isolated_uploads_dir, make_pdf
):
    # Documented limit (D-025): the first 5 bytes must be "%PDF-". Some readers
    # tolerate leading junk; this project deliberately does not.
    content = b"junk\n" + make_pdf(["text"])

    response = upload(client, ("junk.pdf", content))

    assert response.status_code == 415
    assert "%PDF-" in response.json()["results"][0]["error"]
    assert files_in(isolated_uploads_dir) == []


# --- same-name race (R3, R4) -----------------------------------------------------


def _upload_from_threads(name, contents, uploads_dir):
    """Upload `contents[i]` as `name` from one thread each, started together.
    Returns the list of (status_code, content) per thread."""
    barrier = threading.Barrier(len(contents))
    outcomes = [None] * len(contents)

    def worker(index):
        thread_client = TestClient(app)  # one client per thread
        barrier.wait(timeout=10)
        response = upload(thread_client, (name, contents[index]))
        outcomes[index] = (response.status_code, contents[index])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(len(contents))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(outcome is not None for outcome in outcomes), "a thread did not finish"
    return outcomes


def test_race_is_caught_by_the_second_check_when_extraction_is_slow(
    isolated_uploads_dir, make_pdf, monkeypatch
):
    # Both requests pass the first duplicate check (the name is still free) and
    # are held inside extraction until both have arrived. Only then does either
    # try to finish: this exercises the second, final check.
    inside_extraction = threading.Barrier(2)
    real_extract = documents.extract_pages

    def slow_extract(path, file_name):
        inside_extraction.wait(timeout=10)
        return real_extract(path, file_name)

    monkeypatch.setattr(documents, "extract_pages", slow_extract)
    contents = [make_pdf(["version A"]), make_pdf(["version B"])]

    outcomes = _upload_from_threads("race.pdf", contents, isolated_uploads_dir)

    assert sorted(status for status, _ in outcomes) == [200, 409]
    winner = next(content for status, content in outcomes if status == 200)
    assert (isolated_uploads_dir / "race.pdf").read_bytes() == winner
    assert files_in(isolated_uploads_dir) == ["race.pdf"]  # no temp file left


def test_final_check_and_rename_are_one_step(
    isolated_uploads_dir, make_pdf, monkeypatch
):
    # The duplicate check is slowed down AFTER it has computed its answer. Without
    # a lock both threads would get "name is free", then both would call
    # os.replace and the second would silently overwrite the first.
    real_exists = documents._name_exists

    def slow_exists(uploads_dir, name):
        answer = real_exists(uploads_dir, name)
        time.sleep(0.2)
        return answer

    monkeypatch.setattr(documents, "_name_exists", slow_exists)
    contents = [make_pdf(["version A"]), make_pdf(["version B"])]

    outcomes = _upload_from_threads("race.pdf", contents, isolated_uploads_dir)

    assert sorted(status for status, _ in outcomes) == [200, 409]
    winner = next(content for status, content in outcomes if status == 200)
    assert (isolated_uploads_dir / "race.pdf").read_bytes() == winner  # not overwritten
    assert files_in(isolated_uploads_dir) == ["race.pdf"]


def test_rename_happens_while_the_store_lock_is_held(
    client, make_pdf, monkeypatch
):
    # Deterministic, single request: os.replace must run inside _STORE_LOCK.
    # (Check under the lock but rename after releasing it is the bug to catch.)
    real_replace = documents.os.replace
    lock_was_held = []

    def watching_replace(src, dst):
        lock_was_held.append(documents._STORE_LOCK.locked())
        return real_replace(src, dst)

    monkeypatch.setattr(documents.os, "replace", watching_replace)

    response = upload(client, ("held.pdf", make_pdf(["text"])))

    assert response.status_code == 200
    assert lock_was_held == [True]


def test_slow_rename_cannot_let_a_second_upload_overwrite_the_first(
    isolated_uploads_dir, make_pdf, monkeypatch
):
    # The rename itself is slowed down. If it ran outside the lock, the second
    # upload would pass the final check while the first is still renaming, and
    # then overwrite it. With the rename under the lock the second one waits,
    # sees the file and gets 409.
    real_replace = documents.os.replace

    def slow_replace(src, dst):
        time.sleep(0.2)
        return real_replace(src, dst)

    monkeypatch.setattr(documents.os, "replace", slow_replace)
    contents = [make_pdf(["version A"]), make_pdf(["version B"])]

    outcomes = _upload_from_threads("race.pdf", contents, isolated_uploads_dir)

    assert sorted(status for status, _ in outcomes) == [200, 409]
    winner = next(content for status, content in outcomes if status == 200)
    assert (isolated_uploads_dir / "race.pdf").read_bytes() == winner  # not overwritten
    assert files_in(isolated_uploads_dir) == ["race.pdf"]


def test_store_lock_is_released_after_a_rejected_duplicate(
    client, isolated_uploads_dir, make_pdf
):
    upload(client, ("same.pdf", make_pdf(["first"])))
    assert upload(client, ("same.pdf", make_pdf(["second"]))).status_code == 409

    assert documents._STORE_LOCK.acquire(blocking=False), "lock was leaked"
    documents._STORE_LOCK.release()
    assert upload(client, ("other.pdf", make_pdf(["third"]))).status_code == 200
