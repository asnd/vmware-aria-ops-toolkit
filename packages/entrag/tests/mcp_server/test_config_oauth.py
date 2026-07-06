"""Tests for MCP OAuth2 configuration validation in Settings."""

import pytest
from pydantic import ValidationError

from src.config import Settings


class TestMCPOAuthDefaults:
    """Test default MCP settings."""

    def test_mcp_transport_defaults_to_stdio(self):
        s = Settings()
        assert s.mcp_transport == "stdio"

    def test_mcp_port_defaults_to_8080(self):
        s = Settings()
        assert s.mcp_port == 8080

    def test_mcp_oauth_disabled_by_default(self):
        s = Settings()
        assert s.mcp_oauth_enabled is False

    def test_mcp_oauth_jwt_algorithms_defaults_to_rs256(self):
        s = Settings()
        assert s.mcp_oauth_jwt_algorithms == ["RS256"]

    def test_mcp_oauth_leeway_defaults_to_30(self):
        s = Settings()
        assert s.mcp_oauth_leeway_seconds == 30

    def test_mcp_oauth_jwks_cache_ttl_defaults_to_300(self):
        s = Settings()
        assert s.mcp_oauth_jwks_cache_ttl == 300


class TestMCPOAuthValidation:
    """Test OAuth validation rules."""

    def test_oauth_requires_http_transport(self):
        with pytest.raises(ValidationError, match="MCP_OAUTH_ENABLED requires MCP_TRANSPORT=http"):
            Settings(
                mcp_oauth_enabled=True,
                mcp_transport="stdio",
                mcp_oauth_issuer_url="https://keycloak.example.com/realms/test",
                mcp_oauth_resource_server_url="http://localhost:8080",
                mcp_oauth_jwks_url="https://keycloak.example.com/realms/test/protocol/openid-connect/certs",
            )

    def test_oauth_requires_issuer_url(self):
        with pytest.raises(ValidationError, match="MCP_OAUTH_ISSUER_URL"):
            Settings(
                mcp_oauth_enabled=True,
                mcp_transport="http",
                mcp_oauth_resource_server_url="http://localhost:8080",
                mcp_oauth_jwks_url="https://keycloak.example.com/realms/test/protocol/openid-connect/certs",
            )

    def test_oauth_requires_resource_server_url(self):
        with pytest.raises(ValidationError, match="MCP_OAUTH_RESOURCE_SERVER_URL"):
            Settings(
                mcp_oauth_enabled=True,
                mcp_transport="http",
                mcp_oauth_issuer_url="https://keycloak.example.com/realms/test",
                mcp_oauth_jwks_url="https://keycloak.example.com/realms/test/protocol/openid-connect/certs",
            )

    def test_oauth_requires_jwt_key_or_jwks_url(self):
        with pytest.raises(ValidationError, match="MCP_OAUTH_JWT_KEY.*MCP_OAUTH_JWKS_URL"):
            Settings(
                mcp_oauth_enabled=True,
                mcp_transport="http",
                mcp_oauth_issuer_url="https://keycloak.example.com/realms/test",
                mcp_oauth_resource_server_url="http://localhost:8080",
            )

    def test_oauth_rejects_both_jwt_key_and_jwks_url(self):
        with pytest.raises(ValidationError, match="only one of"):
            Settings(
                mcp_oauth_enabled=True,
                mcp_transport="http",
                mcp_oauth_issuer_url="https://keycloak.example.com/realms/test",
                mcp_oauth_resource_server_url="http://localhost:8080",
                mcp_oauth_jwt_key="a" * 32,
                mcp_oauth_jwks_url="https://keycloak.example.com/realms/test/protocol/openid-connect/certs",
                mcp_oauth_jwt_algorithms=["HS256"],
            )

    def test_oauth_rejects_hmac_with_jwks(self):
        with pytest.raises(ValidationError, match="HMAC algorithms.*incompatible with JWKS"):
            Settings(
                mcp_oauth_enabled=True,
                mcp_transport="http",
                mcp_oauth_issuer_url="https://keycloak.example.com/realms/test",
                mcp_oauth_resource_server_url="http://localhost:8080",
                mcp_oauth_jwks_url="https://keycloak.example.com/realms/test/protocol/openid-connect/certs",
                mcp_oauth_jwt_algorithms=["HS256"],
            )

    def test_oauth_rejects_short_hmac_key(self):
        with pytest.raises(ValidationError, match="at least 32 bytes"):
            Settings(
                mcp_oauth_enabled=True,
                mcp_transport="http",
                mcp_oauth_issuer_url="https://keycloak.example.com/realms/test",
                mcp_oauth_resource_server_url="http://localhost:8080",
                mcp_oauth_jwt_key="tooshort",
                mcp_oauth_jwt_algorithms=["HS256"],
            )

    def test_oauth_valid_with_jwks(self):
        """Should succeed with asymmetric algo + JWKS URL."""
        s = Settings(
            mcp_oauth_enabled=True,
            mcp_transport="http",
            mcp_oauth_issuer_url="https://keycloak.example.com/realms/test",
            mcp_oauth_resource_server_url="http://localhost:8080",
            mcp_oauth_jwks_url="https://keycloak.example.com/realms/test/protocol/openid-connect/certs",
            mcp_oauth_jwt_algorithms=["RS256"],
        )
        assert s.mcp_oauth_enabled is True

    def test_oauth_valid_with_hmac_key(self):
        """Should succeed with HS256 + a long enough key."""
        key = "a" * 32
        s = Settings(
            mcp_oauth_enabled=True,
            mcp_transport="http",
            mcp_oauth_issuer_url="https://keycloak.example.com/realms/test",
            mcp_oauth_resource_server_url="http://localhost:8080",
            mcp_oauth_jwt_key=key,
            mcp_oauth_jwt_algorithms=["HS256"],
        )
        assert s.mcp_oauth_jwt_key == key


class TestMCPOAuthStringListParsing:
    """Test the normalize_string_list validator."""

    def test_comma_separated_scopes(self):
        s = Settings(mcp_oauth_required_scopes="read,write,admin")
        assert s.mcp_oauth_required_scopes == ["read", "write", "admin"]

    def test_json_array_scopes(self):
        s = Settings(mcp_oauth_required_scopes='["read", "write"]')
        assert s.mcp_oauth_required_scopes == ["read", "write"]

    def test_empty_string_scopes(self):
        s = Settings(mcp_oauth_required_scopes="")
        assert s.mcp_oauth_required_scopes == []

    def test_list_passthrough(self):
        s = Settings(mcp_oauth_required_scopes=["a", "b"])
        assert s.mcp_oauth_required_scopes == ["a", "b"]

    def test_comma_separated_algorithms(self):
        s = Settings(mcp_oauth_jwt_algorithms="RS256,ES256")
        assert s.mcp_oauth_jwt_algorithms == ["RS256", "ES256"]
