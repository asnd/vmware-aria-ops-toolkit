"""OAuth 2.0 bearer-token verification for the EntRAG MCP HTTP transport.

Validates JWT bearer tokens issued by an external OAuth 2.x / OIDC provider
(e.g. Keycloak). Follows the same pattern as ariaops-mcp/http_auth.py so both
servers can share a single Keycloak realm and client configuration.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import jwt
from jwt import PyJWKClient
from mcp.server.auth.provider import AccessToken, TokenVerifier

from src.config import Settings

logger = logging.getLogger(__name__)


def _normalize_url_claim(value: object) -> str | None:
    """Strip trailing slashes for consistent URL comparison."""
    if value is None:
        return None
    text = str(value).strip()
    normalized = text.rstrip("/")
    return normalized or text


def _extract_scopes(claims: dict[str, Any]) -> list[str]:
    """Extract scopes from either 'scope' (string) or 'scp' (list) claims."""
    raw_scopes = claims.get("scope", claims.get("scp", []))
    if isinstance(raw_scopes, str):
        return [scope for scope in raw_scopes.split() if scope]
    if isinstance(raw_scopes, list):
        return [str(scope) for scope in raw_scopes if str(scope)]
    return []


class JWTTokenVerifier(TokenVerifier):
    """Validate JWT bearer tokens issued by an external OAuth 2.x provider (e.g. Keycloak)."""

    def __init__(self, settings: Settings):
        self._issuer = _normalize_url_claim(settings.mcp_oauth_issuer_url) or ""
        self._audience = _normalize_url_claim(
            settings.mcp_oauth_audience or settings.mcp_oauth_resource_server_url
        )
        self._jwt_key = settings.mcp_oauth_jwt_key or ""
        self._algorithms = settings.mcp_oauth_jwt_algorithms
        self._leeway = settings.mcp_oauth_leeway_seconds
        self._jwks_client: PyJWKClient | None = None
        if settings.mcp_oauth_jwks_url is not None:
            self._jwks_client = PyJWKClient(
                str(settings.mcp_oauth_jwks_url),
                cache_keys=True,
                lifespan=settings.mcp_oauth_jwks_cache_ttl,
            )

    async def _resolve_signing_key(self, token: str) -> str:
        """Resolve the signing key from JWKS endpoint or static secret."""
        if self._jwks_client is None:
            return self._jwt_key
        # PyJWKClient.get_signing_key_from_jwt is sync (urllib + parsing).
        # Run off-loop so we don't block the event loop on cache misses.
        signing_key = await asyncio.to_thread(
            self._jwks_client.get_signing_key_from_jwt, token
        )
        return signing_key.key

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a bearer token and return structured access info, or None on failure."""
        if not token or not isinstance(token, str):
            logger.warning("Rejected empty or non-string MCP OAuth bearer token")
            return None

        try:
            key = await self._resolve_signing_key(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=self._algorithms,
                leeway=self._leeway,
                # We do manual issuer/audience validation below for better logging.
                options={"verify_iss": False, "verify_aud": False},
            )
        except jwt.PyJWKClientError as exc:
            logger.warning("Rejected MCP OAuth bearer token (JWKS lookup failed): %s", exc)
            return None
        except jwt.InvalidTokenError as exc:
            logger.warning("Rejected MCP OAuth bearer token: %s", exc)
            return None

        # Manual issuer check
        issuer = _normalize_url_claim(claims.get("iss"))
        if issuer != self._issuer:
            logger.warning(
                "Rejected MCP OAuth bearer token with unexpected issuer: got %r, expected %r",
                issuer,
                self._issuer,
            )
            return None

        # Manual audience check
        audience_claim = claims.get("aud")
        audiences = (
            [_normalize_url_claim(item) for item in audience_claim]
            if isinstance(audience_claim, list)
            else [_normalize_url_claim(audience_claim)]
        )
        if self._audience and self._audience not in audiences:
            logger.warning("Rejected MCP OAuth bearer token with unexpected audience")
            return None

        # Extract client identity (Keycloak uses azp, others may use client_id/appid/sub)
        client_id = (
            claims.get("client_id")
            or claims.get("azp")
            or claims.get("appid")
            or claims.get("sub")
        )
        if not client_id:
            logger.warning("Rejected MCP OAuth bearer token without client identity claim")
            return None

        return AccessToken(
            token=token,
            client_id=str(client_id),
            scopes=_extract_scopes(claims),
            expires_at=claims.get("exp"),
            resource=self._audience,
        )
