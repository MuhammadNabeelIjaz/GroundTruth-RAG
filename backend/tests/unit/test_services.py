from backend.config import settings
from backend.retrieval import services
from tests.mocks.fake_embedder import FakeEmbedder
from backend.retrieval.st_embedder import SentenceTransformerEmbedder
from backend.retrieval.vector_store import open_collection_or_none


def test_without_override_a_lazy_sentence_transformer_embedder_is_cached(monkeypatch):
    services.reset_caches()
    monkeypatch.setattr(settings, "embedding_model", "some/model")
    monkeypatch.setattr(settings, "embedding_batch_size", 8)
    first = services.get_embedder()
    assert isinstance(first, SentenceTransformerEmbedder)  # constructing loads nothing
    assert first.model_name == "some/model" and services.get_embedder() is first


def test_store_is_cached_per_configuration(tmp_path, monkeypatch):
    services.set_embedder_override(FakeEmbedder(dimension=8))
    first = services.get_store()
    assert services.get_store() is first
    monkeypatch.setattr(settings, "chroma_dir", tmp_path / "other")
    assert services.get_store() is not first
    services.set_embedder_override(FakeEmbedder(dimension=16))
    assert services.get_store() is not first


def test_reset_clears_the_override_and_caches():
    services.set_embedder_override(FakeEmbedder())
    services.get_store()
    services.reset_caches()
    assert not services._stores and services._override is None


def test_open_collection_or_none_when_folder_exists_but_collection_does_not(tmp_path):
    (tmp_path / "chroma").mkdir()
    assert open_collection_or_none(tmp_path / "chroma", "document_chunks") is None
