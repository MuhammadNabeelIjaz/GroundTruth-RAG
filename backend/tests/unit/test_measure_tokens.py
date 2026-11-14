import pytest

from tests.mocks.fake_embedder import FakeEmbedder
from scripts import measure_tokens


def test_measure_reports_distribution_and_over_limit(tmp_path, make_pdf):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(make_pdf(["one two three", "four five"]))
    stats = measure_tokens.measure([pdf], FakeEmbedder(max_tokens=6), 800, 120)
    assert stats == {"chunks": 2, "limit": 6, "min": 4, "median": 4, "p95": 5, "max": 5,
                     "over_limit": 0, "chars_per_token": 2.44}
    assert measure_tokens.measure([pdf], FakeEmbedder(max_tokens=4), 800, 120)["over_limit"] == 1


def test_measure_with_no_chunks(tmp_path, make_pdf):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(make_pdf(["text"]))
    assert measure_tokens.measure([], FakeEmbedder(), 800, 120) == {"chunks": 0}


@pytest.mark.parametrize("over,code", [(0, 0), (1, 1)])
def test_main_exit_code_and_output(monkeypatch, capsys, tmp_path, make_pdf, over, code):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(make_pdf(["x"]))
    monkeypatch.setattr(measure_tokens, "SentenceTransformerEmbedder", lambda *a: FakeEmbedder())
    monkeypatch.setattr(measure_tokens, "measure", lambda *a: {"chunks": 1, "over_limit": over})
    assert measure_tokens.main([str(pdf), "--size", "200", "--overlap", "20"]) == code
    out = capsys.readouterr().out
    assert "chunk_size=200 overlap=20" in out and f"over_limit: {over}" in out
