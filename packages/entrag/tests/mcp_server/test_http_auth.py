"""Tests for the JWT token verifier (OAuth2 bearer-token validation)."""

from __future__ import annotations

import time

import jwt
import pytest

from src.config import Settings
from src.mcp_server.http_auth import (
    JWTTokenVerifier,
    _extract_scopes,
    _normalize_url_claim,
)


class TestNormalizeUrlClaim:
    """Test URL normalization helper."""

    def test_none_returns_none(self):
        assert _normalize_url_claim(None) is None

    def test_strips_trailing_slash(self):
        assert _normalize_url_claim("https://example.com/") == "https://example.com"

    def test_strips_whitespace(self):
        assert _normalize_url_claim("  https://example.com  ") == "https://example.com"

    def test_multiple_trailing_slashes(self):
        assert _normalize_url_claim("https://example.com///") == "https://example.com"

    def test_empty_after_strip_returns_original(self):
        # Edge case: "/" only -> normalized to empty, returns original "/"
        assert _normalize_url_claim("/") == "/"


class TestExtractScopes:
    """Test scope extraction from JWT claims."""

    def test_space_separated_string(self):
        claims = {"scope": "read write admin"}
        assert _extract_scopes(claims) == ["read", "write", "admin"]

    def test_scp_list(self):
        claims = {"scp": ["read", "write"]}
        assert _extract_scopes(claims) == ["read", "write"]

    def test_empty_claims(self):
        assert _extract_scopes({}) == []

    def test_empty_scope_string(self):
        claims = {"scope": ""}
        assert _extract_scopes(claims) == []

    def test_scope_takes_priority_over_scp(self):
        claims = {"scope": "a b", "scp": ["x", "y"]}
        assert _extract_scopes(claims) == ["a", "b"]


@pytest.fixture
def hmac_settings() -> Settings:
    """Settings configured for HMAC (HS256) JWT validation."""
    return Settings(
        mcp_oauth_enabled=True,
        mcp_transport="http",
        mcp_oauth_issuer_url="https://keycloak.example.com/realms/test",
        mcp_oauth_resource_server_url="http://localhost:8080",
        mcp_oauth_jwt_key="a" * 32,
        mcp_oauth_jwt_algorithms=["HS256"],
    )


@pytest.fixture
def verifier(hmac_settings: Settings) -> JWTTokenVerifier:
    """Create a verifier using HMAC settings."""
    return JWTTokenVerifier(hmac_settings)


def _make_token(
    secret: str = "a" * 32,
    issuer: str = "https://keycloak.example.com/realms/test",
    audience: str = "http://localhost:8080",
    client_id: str = "test-client",
    scopes: str = "read write",
    algorithm: str = "HS256",
    expired: bool = False,
) -> str:
    """Create a test JWT token."""
    now = int(time.time())
    payload = {
        "iss": issuer,
        "aud": audience,
        "azp": client_id,
        "scope": scopes,
        "iat": now,
        "exp": now + (3600 if not expired else -3600),
        "sub": "user-123",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


class TestJWTTokenVerifier:
    """Test the JWTTokenVerifier class."""

    @pytest.mark.asyncio
    async def test_valid_token(self, verifier: JWTTokenVerifier):
        token = _make_token()
        result = await verifier.verify_token(token)
        assert result is not None
        assert result.client_id == "test-client"
        assert "read" in result.scopes
        assert "write" in result.scopes

    @pytest.mark.asyncio
    async def test_empty_token_rejected(self, verifier: JWTTokenVerifier):
        result = await verifier.verify_token("")
        assert result is None

    @pytest.mark.asyncio
    async def test_none_token_rejected(self, verifier: JWTTokenVerifier):
        result = await verifier.verify_token(None)  # type: ignore[arg-type]
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_token_string_rejected(self, verifier: JWTTokenVerifier):
        result = await verifier.verify_token("not.a.jwt")
        assert result is None

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, verifier: JWTTokenVerifier):
        token = _make_token(expired=True)
        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_wrong_issuer_rejected(self, verifier: JWTTokenVerifier):
        token = _make_token(issuer="https://wrong-issuer.com/realms/other")
        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_wrong_audience_rejected(self, verifier: JWTTokenVerifier):
        token = _make_token(audience="https://wrong-audience.com")
        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_wrong_secret_rejected(self, verifier: JWTTokenVerifier):
        token = _make_token(secret="b" * 32)
        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_token_without_client_id_rejected(self, verifier: JWTTokenVerifier):
        """Token with no client_id/azp/appid/sub should be rejected."""
        now = int(time.time())
        payload = {
            "iss": "https://keycloak.example.com/realms/test",
            "aud": "http://localhost:8080",
            "scope": "read",
            "iat": now,
            "exp": now + 3600,
            # No azp, client_id, appid, or sub
        }
        token = jwt.encode(payload, "a" * 32, algorithm="HS256")
        result = await verifier.verify_token(token)
        assert result is None

    @pytest.mark.asyncio
    async def test_audience_list_accepted(self, verifier: JWTTokenVerifier):
        """Token with audience as a list should work."""
        now = int(time.time())
        payload = {
            "iss": "https://keycloak.example.com/realms/test",
            "aud": ["http://localhost:8080", "other-service"],
            "azp": "my-client",
            "scope": "read",
            "iat": now,
            "exp": now + 3600,
        }
        token = jwt.encode(payload, "a" * 32, algorithm="HS256")
        result = await verifier.verify_token(token)
        assert result is not None
        assert result.client_id == "my-client"

    @pytest.mark.asyncio
    async def test_client_id_fallback_order(self, verifier: JWTTokenVerifier):
        """Should try client_id -> azp -> appid -> sub."""
        now = int(time.time())
        payload = {
            "iss": "https://keycloak.example.com/realms/test",
            "aud": "http://localhost:8080",
            "appid": "from-appid",
            "scope": "read",
            "iat": now,
            "exp": now + 3600,
        }
        token = jwt.encode(payload, "a" * 32, algorithm="HS256")
        result = await verifier.verify_token(token)
        assert result is not None
        assert result.client_id == "from-appid"

    @pytest.mark.asyncio
    async def test_no_audience_enforcement_when_not_configured(self):
        """If audience is not set, any audience in the token should be accepted."""
        settings = Settings(
            mcp_oauth_enabled=True,
            mcp_transport="http",
            mcp_oauth_issuer_url="https://keycloak.example.com/realms/test",
            mcp_oauth_resource_server_url="http://localhost:8080",
            mcp_oauth_jwt_key="a" * 32,
            mcp_oauth_jwt_algorithms=["HS256"],
            mcp_oauth_audience=None,
        )
        # Override resource_server_url to None as well to test no-enforcement
        settings_dict = settings.model_dump()
        settings_dict["mcp_oauth_resource_server_url"] = None
        # Reconstruct without validation to bypass the model_validator
        v = JWTTokenVerifier.__new__(JWTTokenVerifier)
        v._issuer = "https://keycloak.example.com/realms/test"
        v._audience = None
        v._jwt_key = "a" * 32
        v._algorithms = ["HS256"]
        v._leeway = 30
        v._jwks_client = None

        token = _make_token(audience="any-audience-at-all")
        result = await v.verify_token(token)
        assert result is not None
