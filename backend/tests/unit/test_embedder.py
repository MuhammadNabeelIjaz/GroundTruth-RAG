import math

import pytest

from backend.retrieval.embedder import (
    EmbeddedChunk,
    Embedder,
    TokenLimitExceeded,
    check_normalized,
)
from tests.mocks.fake_embedder import FakeEmbedder
from backend.retrieval.st_embedder import SentenceTransformerEmbedder


def test_fake_vectors_are_normalised_and_deterministic():
    e = FakeEmbedder(dimension=16)
    a = e.embed_documents(["hello world"])[0]
    b = e.embed_documents(["hello world"])[0]
    assert a == b
    assert math.isclose(sum(x * x for x in a.vector), 1.0, abs_tol=1e-9)
    assert len(a.vector) == 16 and isinstance(a, EmbeddedChunk)


def test_shared_words_give_closer_vectors():
    e = FakeEmbedder()
    q = e.embed_query("annual leave policy")
    near = e.embed_documents(["annual leave policy days"])[0].vector
    far = e.embed_documents(["quarterly revenue chart"])[0].vector
    dot = lambda u, v: sum(x * y for x, y in zip(u, v))
    assert dot(q, near) > dot(q, far)


def test_empty_text_still_gives_a_unit_vector():
    v = FakeEmbedder().embed_documents([""])[0].vector
    assert math.isclose(sum(x * x for x in v), 1.0)


def test_empty_list_returns_empty_without_calling_the_model():
    e = FakeEmbedder()
    assert e.embed_documents([]) == []
    assert e.document_calls == []


def test_token_count_includes_special_tokens():
    assert FakeEmbedder().count_tokens("a b c") == 5


def test_over_limit_text_raises_and_nothing_is_embedded():
    e = FakeEmbedder(max_tokens=10)
    ok, too_long = "one two", " ".join(["w"] * 9)  # 9 + 2 = 11 tokens
    with pytest.raises(TokenLimitExceeded) as info:
        e.embed_documents([ok, too_long])
    assert info.value.over_limit == {1: 11}
    assert info.value.max_tokens == 10
    assert "truncate" in str(info.value)
    assert e.document_calls == []  # checked BEFORE embedding


def test_exactly_at_limit_is_allowed():
    e = FakeEmbedder(max_tokens=10)
    assert e.embed_documents([" ".join(["w"] * 8)])[0].token_count == 10


def test_query_over_limit_raises():
    with pytest.raises(TokenLimitExceeded):
        FakeEmbedder(max_tokens=3).embed_query("a b c d")


def test_query_and_document_paths_are_separate():
    e = FakeEmbedder()
    e.embed_query("q")
    e.embed_documents(["d"])
    assert e.query_calls == ["q"] and e.document_calls == [["d"]]


def test_wrong_number_of_vectors_is_an_error():
    class Bad(FakeEmbedder):
        def _encode(self, texts, *, is_query):
            return []

    with pytest.raises(RuntimeError):
        Bad().embed_documents(["x"])


def test_unnormalised_output_is_rejected():
    class Bad(FakeEmbedder):
        def _encode(self, texts, *, is_query):
            return [[2.0] + [0.0] * (self.dimension - 1) for _ in texts]

    with pytest.raises(ValueError, match="normalised"):
        Bad().embed_documents(["x"])


@pytest.mark.parametrize(
    "vector,message",
    [([1.0, 0.0], "expected 3"), ([float("nan"), 0.0, 0.0], "NaN"), ([0.0, 0.0, 0.0], "normalised")],
)
def test_check_normalized_rejects_bad_vectors(vector, message):
    with pytest.raises(ValueError, match=message):
        check_normalized(vector, 3)


def test_interface_is_abstract():
    with pytest.raises(TypeError):
        Embedder()


# ---- SentenceTransformerEmbedder with an injected stub model -------------


class StubTokenizer:
    def __call__(self, text, add_special_tokens, truncation):
        assert add_special_tokens is True and truncation is False
        return {"input_ids": list(range(len(text.split()) + 2))}


class StubModel:
    max_seq_length = 8
    tokenizer = StubTokenizer()

    def __init__(self):
        self.calls = []

    def get_sentence_embedding_dimension(self):
        return 3

    def encode(self, texts, **kwargs):
        self.calls.append(("encode", kwargs))
        return [[1.0, 0.0, 0.0] for _ in texts]


class NewApiModel(StubModel):
    def get_embedding_dimension(self):
        return 3

    def encode_query(self, texts, **kwargs):
        self.calls.append(("encode_query", kwargs))
        return [[0.0, 1.0, 0.0] for _ in texts]

    def encode_document(self, texts, **kwargs):
        self.calls.append(("encode_document", kwargs))
        return [[0.0, 0.0, 1.0] for _ in texts]


def test_st_embedder_reads_limits_from_the_model_and_embeds():
    model = StubModel()
    e = SentenceTransformerEmbedder("stub", batch_size=4, model=model)
    assert (e.model_name, e.dimension, e.max_tokens) == ("stub", 3, 8)
    assert e.count_tokens("a b c") == 5
    assert e.embed_documents(["a b"])[0].vector == [1.0, 0.0, 0.0]
    assert model.calls[0][1]["normalize_embeddings"] is True
    assert model.calls[0][1]["batch_size"] == 4


def test_st_embedder_refuses_to_truncate():
    model = StubModel()
    e = SentenceTransformerEmbedder("stub", model=model)
    with pytest.raises(TokenLimitExceeded):
        e.embed_documents([" ".join(["w"] * 7)])  # 9 tokens > 8
    assert model.calls == []


def test_st_embedder_prefers_new_encode_methods():
    model = NewApiModel()
    e = SentenceTransformerEmbedder("stub", model=model)
    assert e.dimension == 3
    assert e.embed_query("q") == [0.0, 1.0, 0.0]
    assert e.embed_documents(["d"])[0].vector == [0.0, 0.0, 1.0]
    assert [c[0] for c in model.calls] == ["encode_query", "encode_document"]


def test_st_embedder_loads_lazily_and_only_once(monkeypatch):
    import sys
    import types

    loaded = []

    class Fake(StubModel):
        def __init__(self, name):
            super().__init__()
            loaded.append(name)

    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = Fake
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)

    e = SentenceTransformerEmbedder("some/model")
    assert loaded == []  # nothing loaded at construction
    e.max_tokens, e.dimension
    assert loaded == ["some/model"]


def test_onnx_adapter_mocked(monkeypatch):
    from backend.retrieval.st_embedder import _OnnxMiniLMAdapter

    class FakeTok:
        def __init__(self):
            self.padded = True

        def to_str(self):
            return "fake"

        def encode(self, text):
            class Enc:
                ids = [101, 1, 2, 102]

            return Enc()

        def no_padding(self):
            self.padded = False

        def no_truncation(self):
            pass

    class FakeTokenizerLib:
        @staticmethod
        def from_str(s):
            return FakeTok()

    class FakeChromaONNX:
        def __init__(self):
            self.tokenizer = FakeTok()

        def __call__(self, texts):
            return [[1.0] + [0.0] * 383 for _ in texts]

    monkeypatch.setattr("tokenizers.Tokenizer", FakeTokenizerLib)
    monkeypatch.setattr("chromadb.utils.embedding_functions.ONNXMiniLM_L6_V2", FakeChromaONNX)

    adapter = _OnnxMiniLMAdapter("sentence-transformers/all-MiniLM-L6-v2")
    assert adapter.get_embedding_dimension() == 384
    assert adapter.max_seq_length == 256
    assert adapter.tokenizer("hello world") == {"input_ids": [101, 1, 2, 102]}
    vecs = adapter.encode(["hello world"])
    assert len(vecs) == 1 and len(vecs[0]) == 384


def test_st_embedder_falls_back_to_onnx_when_sentence_transformers_missing(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "sentence_transformers", None)

    class FakeAdapter:
        def __init__(self, name):
            self.name = name
            self.max_seq_length = 256

        def get_embedding_dimension(self):
            return 384

        def tokenizer(self, text, **kw):
            return {"input_ids": [1, 2]}

        def encode(self, texts, **kw):
            return [[1.0] + [0.0] * 383 for _ in texts]

    monkeypatch.setattr("backend.retrieval.st_embedder._OnnxMiniLMAdapter", FakeAdapter)

    e = SentenceTransformerEmbedder("some/model")
    assert e.dimension == 384
    assert e.max_tokens == 256
    assert e.count_tokens("test") == 2
    vec = e.embed_query("test")
    assert len(vec) == 384


@pytest.mark.real_model
def test_real_model_end_to_end():
    pytest.importorskip("sentence_transformers")
    try:
        e = SentenceTransformerEmbedder("sentence-transformers/all-MiniLM-L6-v2")
        e.dimension
    except Exception as exc:  # model not downloadable here
        pytest.skip(f"real model unavailable: {exc}")
    assert e.dimension == 384 and e.max_tokens == 256
    assert len(e.embed_query("annual leave")) == 384
