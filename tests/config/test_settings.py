"""Tests for application configuration."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Settings

_ALL_SETTINGS_ENV_KEYS = [
    "LITELLM_BASE_URL", "LITELLM_API_KEY", "LITELLM_MODEL",
    "EMBEDDING_PROVIDER", "LITELLM_EMBEDDING_MODEL", "LOCAL_EMBEDDING_MODEL",
    "SCRAPER_USE_AUTH", "BROADCOM_USERNAME", "BROADCOM_PASSWORD",
    "SCRAPER_DELAY_SECONDS", "SCRAPER_MAX_ARTICLES", "SCRAPER_OUTPUT_DIR",
    "LANCEDB_PATH", "SERVER_HOST", "SERVER_PORT",
    "RERANKER_MODEL", "RERANKER_TOP_N",
    "RETRIEVAL_SIMILARITY_TOP_K", "RETRIEVAL_HYBRID_ALPHA",
]


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Test that default settings are loaded correctly."""
    # chdir to tmp_path so the project .env is not found, and clear any
    # exported env vars that would shadow the defaults.
    monkeypatch.chdir(tmp_path)
    for key in _ALL_SETTINGS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    settings = Settings()

    # LiteLLM defaults
    assert settings.litellm_base_url == "http://localhost:4000"
    assert settings.litellm_api_key == "sk-placeholder"
    assert settings.litellm_model == "gpt-4o"

    # Embedding defaults
    assert settings.embedding_provider == "litellm"
    assert settings.litellm_embedding_model == "text-embedding-3-small"
    assert settings.local_embedding_model == "BAAI/bge-large-en-v1.5"

    # Scraper defaults
    assert settings.scraper_use_auth is False
    assert settings.broadcom_username == ""
    assert settings.broadcom_password.get_secret_value() == ""
    assert settings.scraper_delay_seconds == 3.0
    assert settings.scraper_max_articles == 100
    assert settings.scraper_output_dir == Path("./data/raw")

    # LanceDB defaults
    assert settings.lancedb_path == Path("./data/lancedb")

    # Web server defaults
    assert settings.server_host == "0.0.0.0"
    assert settings.server_port == 7860

    # Reranker defaults
    assert settings.reranker_model == "cross-encoder/ms-marco-MiniLM-L-6-v2"
    assert settings.reranker_top_n == 5

    # Retrieval defaults
    assert settings.retrieval_similarity_top_k == 10
    assert settings.retrieval_hybrid_alpha == 0.7


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch):
    """Test that settings can be overridden by environment variables."""
    test_cases = [
        ("LITELLM_BASE_URL", "http://custom.local:8000", "litellm_base_url"),
        ("LITELLM_API_KEY", "sk-custom-key", "litellm_api_key"),
        ("LITELLM_MODEL", "gpt-3.5-turbo", "litellm_model"),
        ("EMBEDDING_PROVIDER", "local", "embedding_provider"),
        (
            "LOCAL_EMBEDDING_MODEL",
            "sentence-transformers/all-MiniLM-L6-v2",
            "local_embedding_model",
        ),
        ("SCRAPER_USE_AUTH", "true", "scraper_use_auth"),
        ("BROADCOM_USERNAME", "test@example.com", "broadcom_username"),
        ("BROADCOM_PASSWORD", "secret123", "broadcom_password"),
        ("SCRAPER_DELAY_SECONDS", "5.5", "scraper_delay_seconds"),
        ("SCRAPER_MAX_ARTICLES", "500", "scraper_max_articles"),
        ("RETRIEVAL_SIMILARITY_TOP_K", "20", "retrieval_similarity_top_k"),
        ("RETRIEVAL_HYBRID_ALPHA", "0.5", "retrieval_hybrid_alpha"),
    ]

    for env_var, env_value, attr_name in test_cases:
        monkeypatch.setenv(env_var, env_value)
        settings = Settings()
        # Handle boolean conversion
        if attr_name == "scraper_use_auth":
            assert settings.scraper_use_auth is True
        elif attr_name in ["scraper_delay_seconds", "retrieval_hybrid_alpha"]:
            assert getattr(settings, attr_name) == float(env_value)
        elif attr_name in ["scraper_max_articles", "retrieval_similarity_top_k"]:
            assert getattr(settings, attr_name) == int(env_value)
        elif attr_name == "broadcom_password":
            assert settings.broadcom_password.get_secret_value() == env_value
        else:
            assert getattr(settings, attr_name) == env_value
        monkeypatch.delenv(env_var, raising=False)


def test_settings_from_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test loading settings from .env file."""
    # Clear env vars so they don't shadow values in the test file
    for key in _ALL_SETTINGS_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    env_file = tmp_path / ".test.env"
    env_file.write_text("""
LITELLM_BASE_URL=http://file.test:9000
LITELLM_MODEL=gpt-4
SCRAPER_USE_AUTH=true
BROADCOM_USERNAME=file-user@test.com
SCRAPER_MAX_ARTICLES=75
""")

    # Clear settings cache
    from src.config import get_settings
    get_settings.cache_clear()

    # Save original env_file
    original_env_file = Settings.model_config.get('env_file')

    # Temporarily override the env_file for Settings class
    Settings.model_config['env_file'] = str(env_file)

    try:
        settings = Settings()

        assert settings.litellm_base_url == "http://file.test:9000"
        assert settings.litellm_model == "gpt-4"
        assert settings.scraper_use_auth is True
        assert settings.broadcom_username == "file-user@test.com"
        assert settings.scraper_max_articles == 75
    finally:
        # Restore original config
        Settings.model_config['env_file'] = original_env_file
        get_settings.cache_clear()


def test_settings_validation():
    """Test that invalid values raise validation errors."""
    # Test invalid embedding provider
    with pytest.raises(ValidationError):
        Settings(embedding_provider="invalid")

    # Test invalid scraper delay (negative)
    with pytest.raises(ValidationError):
        Settings(scraper_delay_seconds=-1.0)

    # Test invalid max articles (zero or negative)
    with pytest.raises(ValidationError):
        Settings(scraper_max_articles=0)

    with pytest.raises(ValidationError):
        Settings(scraper_max_articles=-5)

    # Test invalid retrieval alpha (outside 0-1 range)
    with pytest.raises(ValidationError):
        Settings(retrieval_hybrid_alpha=1.5)

    with pytest.raises(ValidationError):
        Settings(retrieval_hybrid_alpha=-0.1)


def test_get_settings_cached():
    """Test that get_settings returns a cached instance."""
    from src.config import get_settings

    # Clear cache first
    get_settings.cache_clear()

    settings1 = get_settings()
    settings2 = get_settings()

    # Should be the same object (cached)
    assert settings1 is settings2

    # Different instance after cache clear
    get_settings.cache_clear()
    settings3 = get_settings()
    assert settings3 is not settings1
