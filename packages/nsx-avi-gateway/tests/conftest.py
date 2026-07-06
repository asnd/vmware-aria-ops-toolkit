"""Pytest configuration and shared fixtures."""

import asyncio

import pytest
from fastapi.testclient import TestClient

AUTH_TEST_PASSWORD = "gateway-auth-secret"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_sites_config():
    """Sample sites configuration for testing."""
    return """
sites:
  - site_id: "test-site-1"
    name: "Test Site 1"
    region: "us-east"
    nsxt:
      manager_url: "https://nsxt-test1.example.com"
      username: "test-user"
      password: "test-site-secret"
      verify_ssl: false
    avi:
      controller_url: "https://avi-test1.example.com"
      username: "test-user"
      password: "test-site-secret"
      tenant: "admin"
      api_version: "22.1.3"
    tags:
      environment: test
      tier: bronze

  - site_id: "test-site-2"
    name: "Test Site 2"
    region: "us-west"
    nsxt:
      manager_url: "https://nsxt-test2.example.com"
      username: "test-user"
      password: "test-site-secret"
      verify_ssl: false
    tags:
      environment: test
      tier: silver
"""


@pytest.fixture
def sample_allowlist_config():
    """Sample operations allowlist for testing."""
    return """
nsxt:
  segments:
    - create
    - read
    - update

  tier1_gateways:
    - create
    - read

  blocked:
    - "tier0_gateways.*"
    - "segments.delete"

avi:
  virtual_services:
    - create
    - read
    - update

  pools:
    - create
    - read
    - update
    - delete

  blocked:
    - "virtual_services.delete"

role_overrides:
  admin:
    additional_permissions:
      - "nsxt.segments.delete"
"""


@pytest.fixture
def temp_sites_config(tmp_path, sample_sites_config):
    """Create temporary sites configuration file."""
    sites_file = tmp_path / "sites.yml"
    sites_file.write_text(sample_sites_config)
    return sites_file


@pytest.fixture
def temp_allowlist_config(tmp_path, sample_allowlist_config):
    """Create temporary allowlist configuration file."""
    allowlist_file = tmp_path / "operations_allowlist.yml"
    allowlist_file.write_text(sample_allowlist_config)
    return allowlist_file


@pytest.fixture
def auth_test_password():
    """Plaintext password used for auth-related tests."""
    return AUTH_TEST_PASSWORD


@pytest.fixture(autouse=True)
def configured_auth_settings(monkeypatch):
    """Configure explicit auth settings for every test."""
    from app.auth.oauth2 import get_password_hash
    from app.config import settings

    hashed_password = get_password_hash(AUTH_TEST_PASSWORD)
    monkeypatch.setattr(settings, "jwt_secret_key", "test-secret-key-for-testing-only")
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(settings, "jwt_private_key_path", None)
    monkeypatch.setattr(settings, "jwt_public_key_path", None)
    monkeypatch.setattr(settings, "admin_password_hash", hashed_password)
    monkeypatch.setattr(settings, "operator_password_hash", hashed_password)
    monkeypatch.setattr(settings, "readonly_password_hash", hashed_password)
    yield settings


@pytest.fixture
def mock_settings(monkeypatch, tmp_path, temp_sites_config, temp_allowlist_config):
    """Override file-backed settings for testing."""
    from app.config import settings

    monkeypatch.setattr(settings, "sites_config_path", temp_sites_config)
    monkeypatch.setattr(settings, "operations_allowlist_path", temp_allowlist_config)
    monkeypatch.setattr(settings, "access_token_expire_minutes", 60)
    monkeypatch.setattr(settings, "job_retention_minutes", 1440)
    monkeypatch.setattr(settings, "job_cleanup_interval_seconds", 300)
    monkeypatch.setattr(settings, "max_concurrent_jobs", 50)
    monkeypatch.setattr(settings, "idempotency_cache_ttl_seconds", 86400)
    monkeypatch.setattr(settings, "log_level", "INFO")
    monkeypatch.setattr(settings, "audit_log_path", tmp_path / "audit.jsonl")
    yield settings


@pytest.fixture
def test_client(mock_settings):
    """FastAPI test client with mocked settings."""
    # Import here to ensure settings are mocked
    from app.main import app

    return TestClient(app)


@pytest.fixture
def test_user_admin():
    """Test admin user."""
    from app.models.auth import User

    return User(
        username="test-admin",
        roles=["admin", "operator"],
        permissions=["nsxt:*", "avi:*"],
        disabled=False,
    )


@pytest.fixture
def test_user_operator():
    """Test operator user."""
    from app.models.auth import User

    return User(
        username="test-operator",
        roles=["operator"],
        permissions=[
            "nsxt:segment:create",
            "nsxt:segment:read",
            "avi:pool:*",
        ],
        disabled=False,
    )


@pytest.fixture
def test_user_readonly():
    """Test readonly user."""
    from app.models.auth import User

    return User(
        username="test-readonly",
        roles=["readonly"],
        permissions=["nsxt:*:read", "avi:*:read"],
        disabled=False,
    )
