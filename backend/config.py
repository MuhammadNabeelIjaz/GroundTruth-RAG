"""Application settings.

Values are read from environment variables (or a local `.env` file).
Every setting has a safe default, so the app starts without any configuration.
New settings (LLM key, chunk size, ...) are added here in later stages.

Environment variable names are the field names in upper case, e.g.
`LOG_LEVEL`, `UPLOADS_DIR`, `CHROMA_DIR`, `MAX_UPLOAD_MB`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `EMBEDDING_MODEL`,
`EMBEDDING_BATCH_SIZE`, `CHROMA_COLLECTION_NAME`, `RETRIEVAL_TOP_K`, `MIN_SIMILARITY`,
`GROQ_API_KEY`, `LLM_MODEL`, `LLM_TEMPERATURE`, `LLM_TIMEOUT_SECONDS`,
`CONVERSATIONS_DB_PATH`, `MAX_HISTORY_TURNS`.
"""

from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.ingestion.chunker import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_OVERLAP,
    validate_chunk_settings,
)

# The repository root (the folder that contains `backend/`). Defaults below are
# built from it, so the app finds its data folders no matter which directory
# it was started from.
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            BACKEND_DIR / ".env",
            ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",  # ignore variables this stage does not use yet
    )

    app_name: str = "rag-qa-assistant"
    app_version: str = "0.1.0"

    # CORS allowed origins (frontend web client origins only).
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # DEBUG, INFO, WARNING, ERROR or CRITICAL (case-insensitive).
    log_level: str = "INFO"

    # Runtime data folders. Their contents are git-ignored. Folders are created
    # when first needed (Stage 1 / Stage 3), not at import time.
    uploads_dir: Path = DATA_DIR / "uploads"
    chroma_dir: Path = DATA_DIR / "chroma"

    # Largest accepted PDF upload, in megabytes (must be at least 1).
    max_upload_mb: int = Field(default=20, ge=1)

    # Chunking (Stage 2), in characters. 800 / 120 are starting values (D-002, D-031);
    # Token-aware chunking enforces the embedding model's token limits (<= 256 tokens)
    chunk_size: int = DEFAULT_CHUNK_SIZE
    chunk_overlap: int = DEFAULT_OVERLAP
    token_aware_chunking: bool = False

    # Embeddings and vector store (Stage 3).
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_batch_size: int = Field(default=32, ge=1, le=1024)
    chroma_collection_name: str = "document_chunks"

    # Retrieval (Stage 4).
    retrieval_top_k: int = Field(default=5, ge=1, le=100)
    min_similarity: float = Field(default=0.0, ge=-1.0, le=1.0)

    # LLM / Groq API (Stage 5).
    groq_api_key: str | None = None
    llm_model: str = "qwen/qwen3.8-27b"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    llm_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)

    # Conversations & Chat History (Stage 7).
    conversations_db_path: Path = DATA_DIR / "conversations.db"
    max_history_turns: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def _check_chunk_settings(self) -> "Settings":
        # Fail at startup with a clear message (ValueError becomes a validation error).
        validate_chunk_settings(self.chunk_size, self.chunk_overlap)
        return self

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
