"""Real embedder: sentence-transformers (default all-MiniLM-L6-v2).

`sentence_transformers` is imported lazily, only when a model is actually
loaded, so tests (which use FakeEmbedder) never need torch. The model's own
tokenizer counts tokens (special tokens included) and `max_seq_length` is read
from the model, not hard-coded. Embedding calls are serialised by a lock.

If `sentence-transformers` is unavailable (e.g. on Windows environments where
PyTorch wheels exceed the 260-character MAX_PATH limit), it seamlessly falls
back to ChromaDB's built-in ONNX runtime `all-MiniLM-L6-v2` model.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from backend.retrieval.embedder import Embedder

logger = logging.getLogger(__name__)


class _OnnxMiniLMAdapter:
    """Fallback embedding adapter when sentence-transformers / PyTorch is unavailable.

    Uses ChromaDB's built-in ONNX runtime all-MiniLM-L6-v2 model (384 dimensions,
    256 max tokens) without requiring heavy PyTorch dependencies or failing under
    Windows MAX_PATH restrictions.
    """

    def __init__(self, model_name: str) -> None:
        from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2
        from tokenizers import Tokenizer

        self.model_name = model_name
        self._fn = ONNXMiniLM_L6_V2()
        if hasattr(self._fn, "_download_model_if_not_exists"):
            self._fn._download_model_if_not_exists()
        self.max_seq_length = 256
        self._count_tokenizer = Tokenizer.from_str(self._fn.tokenizer.to_str())
        self._count_tokenizer.no_padding()
        self._count_tokenizer.no_truncation()

    def get_embedding_dimension(self) -> int:
        return 384

    def tokenizer(
        self, text: str, add_special_tokens: bool = True, truncation: bool = False
    ) -> dict[str, list[int]]:
        encoded = self._count_tokenizer.encode(text)
        return {"input_ids": encoded.ids}

    def encode(
        self,
        texts: list[str],
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
        show_progress_bar: bool = False,
    ) -> list[Any]:
        return self._fn(texts)


class SentenceTransformerEmbedder(Embedder):
    def __init__(self, model_name: str, batch_size: int = 32, model=None) -> None:
        self._model_name = model_name
        self._batch_size = batch_size
        self._model = model  # injectable (tests); otherwise loaded lazily
        self._load_lock = threading.Lock()
        self._encode_lock = threading.Lock()

    def _get_model(self):
        with self._load_lock:
            if self._model is None:
                logger.info("Loading embedding model %s (first use)", self._model_name)
                try:
                    from sentence_transformers import SentenceTransformer  # lazy: needs torch

                    self._model = SentenceTransformer(self._model_name)
                except ImportError:
                    logger.info(
                        "sentence_transformers unavailable; falling back to built-in ONNX runtime (%s)",
                        self._model_name,
                    )
                    self._model = _OnnxMiniLMAdapter(self._model_name)
            return self._model

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        model = self._get_model()
        getter = getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension
        return int(getter())

    @property
    def max_tokens(self) -> int:
        return int(self._get_model().max_seq_length)

    def count_tokens(self, text: str) -> int:
        tokenizer = self._get_model().tokenizer
        return len(tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"])

    def _encode(self, texts: list[str], *, is_query: bool) -> list[list[float]]:
        model = self._get_model()
        with self._encode_lock:
            # sentence-transformers 6 prefers encode_query / encode_document;
            # older versions only have encode.
            name = "encode_query" if is_query else "encode_document"
            encode = getattr(model, name, None) or model.encode
            vectors = encode(
                texts,
                batch_size=self._batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return [[float(x) for x in row] for row in vectors]
