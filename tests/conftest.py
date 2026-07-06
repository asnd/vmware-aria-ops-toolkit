"""Pytest configuration and shared fixtures."""

import os
import tempfile

import pytest
from _pytest.monkeypatch import MonkeyPatch

from src.config import Settings, get_settings


@pytest.fixture
def temp_env_file():
    """Create a temporary .env file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
        f.write("LITELLM_BASE_URL=http://test.local:4000\n")
        f.write("SCRAPER_USE_AUTH=false\n")
        temp_path = f.name

    yield temp_path

    # Cleanup
    os.unlink(temp_path)


@pytest.fixture
def clean_settings(temp_env_file: str, monkeypatch: MonkeyPatch):
    """Provide clean Settings instance for each test.

    Uses monkeypatch to temporarily override the env_file config
    so the Settings class reads from our temporary file.
    """
    # Clear any cached settings
    get_settings.cache_clear()

    # Temporarily override env_file at the class level
    original_env_file = Settings.model_config.get("env_file")
    Settings.model_config["env_file"] = temp_env_file

    try:
        yield get_settings()
    finally:
        # Restore original config
        Settings.model_config["env_file"] = original_env_file
        get_settings.cache_clear()
