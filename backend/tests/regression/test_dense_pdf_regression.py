"""Regression tests for dense technical PDF ingestion and token-aware chunking.

Verifies that high-token-density documents such as technical lecture notes,
slide decks, and tabular documents (e.g. Proxy Marketing - lecture notes.pdf)
upload and index smoothly without triggering 422 ChunksOverTokenLimit, and that
grounded question-answering returns factual answers with valid citations.
"""

from io import BytesIO
import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.generation.answer_service import answer_question
from backend.generation.llm_client import LLMClient
from backend.main import app
from backend.retrieval import services
from tests.mocks.fake_embedder import FakeEmbedder


@pytest.fixture(autouse=True)
def enable_token_aware_chunking(monkeypatch):
    monkeypatch.setattr(settings, "token_aware_chunking", True)


def _create_dense_lecture_notes_pdf() -> bytes:
    """Generate a multi-page PDF with dense technical lecture notes."""
    doc = pymupdf.open()
    
    # Page 1: Dense bullet points and acronyms
    p1 = doc.new_page()
    text_p1 = (
        "Proxy Marketing and Web Automation - Lecture Notes\n\n"
        "1. Residential vs Datacenter Proxies\n"
        "Residential proxies route traffic through residential IP addresses provided by ISPs (e.g. Comcast, AT&T). "
        "Datacenter proxies originate from server farms (AWS, DigitalOcean, Hetzner) and feature lower latency "
        "but higher detection rates due to ASN classification.\n\n"
        "2. IP Rotation and Session Sticky Duration\n"
        "Rotating proxies change IP per HTTP request or after a sticky duration (typically 5m, 10m, or 30m). "
        "Session stickiness is maintained via session-id query parameters or custom HTTP headers (e.g., X-Proxy-Session).\n\n"
        "3. HTTP CONNECT Tunneling and TLS Fingerprinting\n"
        "Modern anti-bot systems (Cloudflare, Akamai, Datadome) inspect JA3/JA4 TLS fingerprints and HTTP/2 settings "
        "frames to detect automated proxy clients."
    )
    p1.insert_textbox(pymupdf.Rect(40, 40, 560, 780), text_p1, fontsize=10)

    # Page 2: Highly token-dense technical parameters & tables
    p2 = doc.new_page()
    text_p2 = (
        "4. Anti-Scraping Defenses & Evading Detection\n\n"
        "Protocols: SOCKS5, HTTP/1.1, HTTP/2, QUIC/HTTP3.\n"
        "Headers required for browser emulation:\n"
        "- User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\n"
        "- Accept: text/html,application/xhtml+xml,application/xml;q=0.9\n"
        "- Accept-Encoding: gzip, deflate, br, zstd\n"
        "- Sec-CH-UA: \"Chromium\";v=\"124\", \"Google Chrome\";v=\"124\"\n"
        "- Sec-Fetch-Dest: document, Sec-Fetch-Mode: navigate\n\n"
        "Bandwidth calculations: Cost = (GB_Transferred * Rate_Per_GB) + Concurrency_Surcharge. "
        "Backconnect proxy pools distribute connections across 10,000+ peer nodes."
    )
    p2.insert_textbox(pymupdf.Rect(40, 40, 560, 780), text_p2, fontsize=10)

    buffer = BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


def _create_simple_pdf(title: str, text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 560, 780), f"{title}\n\n{text}", fontsize=11)
    buffer = BytesIO()
    doc.save(buffer)
    doc.close()
    return buffer.getvalue()


class MockGroqClient(LLMClient):
    """Deterministic LLM mock that cites supplied passages."""

    def __init__(self, answer: str) -> None:
        self.answer = answer

    def generate(self, messages: list[dict[str, str]], **kwargs) -> str:
        return self.answer


def test_dense_lecture_notes_pdf_upload_succeeds_without_422():
    client = TestClient(app)
    pdf_bytes = _create_dense_lecture_notes_pdf()
    file_name = "Proxy Marketing - lecture notes.pdf"

    response = client.post(
        "/documents",
        files=[("files", (file_name, pdf_bytes, "application/pdf"))],
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 1
    result = data["results"][0]

    assert result["success"] is True
    assert result["file_name"] == file_name
    assert result["error"] is None
    assert result["page_count"] == 2
    assert result["chunk_count"] >= 2
    assert result["max_chunk_tokens"] <= 256

    # Verify vector store contents
    store = services.get_store()
    counts = store.file_chunk_counts()
    assert counts.get(file_name) == result["chunk_count"]


def test_multiple_dense_and_short_pdfs_upload_in_single_batch():
    client = TestClient(app)
    dense_bytes = _create_dense_lecture_notes_pdf()
    short_bytes = _create_simple_pdf("Short Guide", "This is a brief introductory overview.")

    response = client.post(
        "/documents",
        files=[
            ("files", ("Proxy Marketing - lecture notes.pdf", dense_bytes, "application/pdf")),
            ("files", ("short_overview.pdf", short_bytes, "application/pdf")),
        ],
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert all(r["success"] is True for r in results)
    assert all(r["max_chunk_tokens"] <= 256 for r in results)


def test_dense_pdf_grounded_answer_and_verifiable_citations():
    client = TestClient(app)
    pdf_bytes = _create_dense_lecture_notes_pdf()
    file_name = "Proxy Marketing - lecture notes.pdf"

    upload_res = client.post(
        "/documents",
        files=[("files", (file_name, pdf_bytes, "application/pdf"))],
    )
    assert upload_res.status_code == 200

    mock_answer = (
        "Residential proxies route traffic through residential IP addresses provided by ISPs, "
        "whereas datacenter proxies originate from server farms like AWS [Passage 1]."
    )
    mock_llm = MockGroqClient(mock_answer)

    result = answer_question(
        "What is the difference between residential and datacenter proxies?",
        llm_client=mock_llm,
    )

    assert result.found is True
    assert "Residential proxies" in result.answer
    assert len(result.citations) >= 1
    assert result.citations[0].file_name == file_name
    assert result.citations[0].page_number == 1
    assert "residential" in result.citations[0].excerpt.lower()
