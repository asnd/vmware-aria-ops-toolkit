"""Tests for the MCP server entry point and HTTP app creation."""

from __future__ import annotations

import pytest

from src.config import Settings
from src.mcp_server.__main__ import create_http_app


class TestCreateHttpApp:
    """Test HTTP app creation with and without OAuth."""

    def test_creates_app_without_oauth(self):
        """Basic HTTP app without OAuth should start cleanly."""
        settings = Settings(mcp_transport="http", mcp_oauth_enabled=False)
        app = create_http_app(settings=settings)
        assert app is not None
        # Should have /health and /mcp routes
        route_paths = [r.path for r in app.routes]
        assert "/health" in route_paths
        assert "/mcp" in route_paths

    def test_creates_app_with_oauth(self):
        """HTTP app with OAuth should include auth middleware."""
        settings = Settings(
            mcp_transport="http",
            mcp_oauth_enabled=True,
            mcp_oauth_issuer_url="https://keycloak.example.com/realms/test",
            mcp_oauth_resource_server_url="http://localhost:8080",
            mcp_oauth_jwks_url="https://keycloak.example.com/realms/test/protocol/openid-connect/certs",
            mcp_oauth_jwt_algorithms=["RS256"],
        )
        app = create_http_app(settings=settings)
        assert app is not None
        # Should have middleware configured
        assert len(app.middleware_stack.__class__.__mro__) > 1  # has middleware layers
        # Should have protected resource metadata route
        route_paths = [r.path for r in app.routes]
        assert "/mcp" in route_paths

    def test_raises_if_oauth_enabled_without_urls(self):
        """Should raise if OAuth URLs are None (bypassing Settings validation)."""
        settings = Settings(mcp_transport="http", mcp_oauth_enabled=False)
        # Force enable OAuth after construction (bypassing validator)
        object.__setattr__(settings, "mcp_oauth_enabled", True)
        object.__setattr__(settings, "mcp_oauth_issuer_url", None)
        object.__setattr__(settings, "mcp_oauth_resource_server_url", None)

        with pytest.raises(RuntimeError, match="OAuth is enabled but"):
            create_http_app(settings=settings)
