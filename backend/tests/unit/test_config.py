import pytest

from backend.config import DATA_DIR, PROJECT_ROOT, Settings

SETTING_VARS = (
    "APP_NAME",
    "APP_VERSION",
    "LOG_LEVEL",
    "UPLOADS_DIR",
    "CHROMA_DIR",
    "MAX_UPLOAD_MB",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "TOKEN_AWARE_CHUNKING",
    "EMBEDDING_MODEL",
    "EMBEDDING_BATCH_SIZE",
    "CHROMA_COLLECTION_NAME",
    "RETRIEVAL_TOP_K",
    "MIN_SIMILARITY",
    "GROQ_API_KEY",
    "LLM_MODEL",
    "LLM_TEMPERATURE",
    "LLM_TIMEOUT_SECONDS",
    "CONVERSATIONS_DB_PATH",
    "MAX_HISTORY_TURNS",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Ignore any settings exported in the developer's shell."""
    for name in SETTING_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults():
    # _env_file=None: ignore the developer's own .env file as well.
    s = Settings(_env_file=None)

    assert s.app_name == "GroundTruth-RAG"
    assert s.log_level == "INFO"
    assert s.uploads_dir == DATA_DIR / "uploads"
    assert s.chroma_dir == DATA_DIR / "chroma"
    assert s.max_upload_mb == 20
    assert s.max_upload_bytes == 20 * 1024 * 1024
    assert (s.chunk_size, s.chunk_overlap) == (800, 120)
    assert s.token_aware_chunking is False
    assert s.retrieval_top_k == 5
    assert s.min_similarity == 0.0
    assert s.groq_api_key is None
    assert s.llm_model == "qwen/qwen3.8-27b"
    assert s.llm_temperature == 0.0
    assert s.llm_timeout_seconds == 30.0
    assert s.conversations_db_path == DATA_DIR / "conversations.db"
    assert s.max_history_turns == 10


def test_environment_variables_override_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("MAX_UPLOAD_MB", "5")

    s = Settings(_env_file=None)

    assert s.log_level == "DEBUG"
    assert s.uploads_dir == tmp_path / "uploads"
    assert s.chroma_dir == tmp_path / "chroma"
    assert s.max_upload_mb == 5


def test_values_are_read_from_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("LOG_LEVEL=WARNING\n", encoding="utf-8")

    s = Settings(_env_file=env_file)

    assert s.log_level == "WARNING"


def test_upload_limit_must_be_positive(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "0")

    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_project_root_is_the_repository_root():
    assert (PROJECT_ROOT / "backend" / "config.py").is_file()


def test_chunk_settings_can_be_overridden(monkeypatch):
    monkeypatch.setenv("CHUNK_SIZE", "500")
    monkeypatch.setenv("CHUNK_OVERLAP", "50")

    s = Settings(_env_file=None)

    assert (s.chunk_size, s.chunk_overlap) == (500, 50)


def test_minimum_chunk_size_and_zero_overlap_are_accepted(monkeypatch):
    monkeypatch.setenv("CHUNK_SIZE", "100")
    monkeypatch.setenv("CHUNK_OVERLAP", "0")

    s = Settings(_env_file=None)

    assert (s.chunk_size, s.chunk_overlap) == (100, 0)


@pytest.mark.parametrize(
    ("size", "overlap"),
    [
        ("99", "0"),  # below the minimum size
        ("800", "-1"),  # negative overlap
        ("800", "800"),  # overlap equal to size
        ("200", "300"),  # overlap larger than size
        ("abc", "10"),  # not a number
    ],
)
def test_invalid_chunk_settings_stop_the_application_from_starting(monkeypatch, size, overlap):
    monkeypatch.setenv("CHUNK_SIZE", size)
    monkeypatch.setenv("CHUNK_OVERLAP", overlap)

    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_llm_settings_can_be_overridden(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key-123")
    monkeypatch.setenv("LLM_MODEL", "meta-llama/llama-3.3-70b-versatile")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.7")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45.0")

    s = Settings(_env_file=None)

    assert s.groq_api_key == "test-key-123"
    assert s.llm_model == "meta-llama/llama-3.3-70b-versatile"
    assert s.llm_temperature == 0.7
    assert s.llm_timeout_seconds == 45.0


@pytest.mark.parametrize(
    ("temp", "timeout"),
    [
        ("-0.1", "30.0"),  # temp < 0.0
        ("2.5", "30.0"),   # temp > 2.0
        ("0.0", "0.5"),    # timeout < 1.0
        ("0.0", "400.0"),  # timeout > 300.0
    ],
)
def test_invalid_llm_settings_raise_validation_error(monkeypatch, temp, timeout):
    monkeypatch.setenv("LLM_TEMPERATURE", temp)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValueError):
        Settings(_env_file=None)



@pytest.mark.parametrize(
    ("top_k", "min_sim"),
    [
        ("0", "0.0"),  # top_k < 1
        ("101", "0.0"),  # top_k > 100
        ("5", "-1.5"),  # min_sim < -1.0
        ("5", "1.5"),  # min_sim > 1.0
    ],
)
def test_invalid_retrieval_settings_raise_validation_error(monkeypatch, top_k, min_sim):
    monkeypatch.setenv("RETRIEVAL_TOP_K", top_k)
    monkeypatch.setenv("MIN_SIMILARITY", min_sim)

    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_conversation_settings_can_be_overridden(monkeypatch, tmp_path):
    db_file = tmp_path / "custom_conversations.db"
    monkeypatch.setenv("CONVERSATIONS_DB_PATH", str(db_file))
    monkeypatch.setenv("MAX_HISTORY_TURNS", "25")

    s = Settings(_env_file=None)
    assert s.conversations_db_path == db_file
    assert s.max_history_turns == 25


@pytest.mark.parametrize("turns", ["0", "-5", "51", "100"])
def test_invalid_max_history_turns_raises_validation_error(monkeypatch, turns):
    monkeypatch.setenv("MAX_HISTORY_TURNS", turns)

    with pytest.raises(ValueError):
        Settings(_env_file=None)


