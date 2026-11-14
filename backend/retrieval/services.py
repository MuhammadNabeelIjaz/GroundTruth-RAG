"""Cached embedder / vector-store factories, keyed by configuration.

Creating a SentenceTransformer or a Chroma client is slow, so each is built
once per distinct configuration. Tests install a FakeEmbedder with
`set_embedder_override` and clear everything with `reset_caches`.
"""

from __future__ import annotations

import threading

from backend.config import settings
from backend.retrieval.embedder import Embedder
from backend.retrieval.st_embedder import SentenceTransformerEmbedder
from backend.retrieval.vector_store import VectorStore

_lock = threading.Lock()
_embedders: dict[tuple, Embedder] = {}
_stores: dict[tuple, VectorStore] = {}
_override: Embedder | None = None


def set_embedder_override(embedder: Embedder | None) -> None:
    global _override
    with _lock:
        _override = embedder


def reset_caches() -> None:
    global _override
    with _lock:
        _embedders.clear()
        _stores.clear()
        _override = None


def get_embedder() -> Embedder:
    with _lock:
        if _override is not None:
            return _override
        key = (settings.embedding_model, settings.embedding_batch_size)
        if key not in _embedders:
            _embedders[key] = SentenceTransformerEmbedder(*key)
        return _embedders[key]


def get_store() -> VectorStore:
    embedder = get_embedder()  # outside the lock: may load the model
    with _lock:
        key = (str(settings.chroma_dir), settings.chroma_collection_name, embedder.model_name, embedder.dimension)
        if key not in _stores:
            _stores[key] = VectorStore(
                chroma_dir=settings.chroma_dir,
                collection_name=settings.chroma_collection_name,
                embedding_model=embedder.model_name,
                dimension=embedder.dimension,
            )
        return _stores[key]
