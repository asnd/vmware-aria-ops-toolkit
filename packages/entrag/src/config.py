"""Application configuration using pydantic-settings.

All settings are loaded from environment variables or .env file.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AnyHttpUrl, Field, SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LiteLLM
    litellm_base_url: str = Field(default="http://localhost:4000")
    litellm_api_key: str = Field(default="sk-placeholder")
    litellm_model: str = Field(default="gpt-4o")

    # Embedding
    embedding_provider: Literal["litellm", "local"] = Field(default="litellm")
    litellm_embedding_model: str = Field(default="text-embedding-3-small")
    local_embedding_model: str = Field(default="BAAI/bge-large-en-v1.5")

    # LanceDB
    lancedb_path: Path = Field(default=Path("./data/lancedb"))

    # Scraper
    scraper_use_auth: bool = Field(default=False)
    broadcom_username: str = Field(default="")
    broadcom_password: SecretStr = Field(default=SecretStr(""))
    scraper_delay_seconds: float = Field(default=3.0, ge=0.0)
    scraper_max_articles: int = Field(default=100, ge=1)
    scraper_output_dir: Path = Field(default=Path("./data/raw"))

    # Web server (Chainlit UI)
    server_host: str = Field(default="0.0.0.0")
    server_port: int = Field(default=7860, ge=1, le=65535)

    # Reranker
    reranker_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2")
    reranker_top_n: int = Field(default=5, ge=1)

    # Retrieval
    retrieval_similarity_top_k: int = Field(default=10, ge=1)
    retrieval_hybrid_alpha: float = Field(default=0.7, ge=0.0, le=1.0)

    # MCP transport
    mcp_transport: Literal["stdio", "http"] = Field(default="stdio")
    mcp_port: int = Field(default=8080, ge=1, le=65535)
    mcp_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO"
    )

    # MCP OAuth2 (Keycloak / any OIDC provider)
    mcp_oauth_enabled: bool = Field(default=False)
    mcp_oauth_issuer_url: AnyHttpUrl | None = Field(default=None)
    mcp_oauth_resource_server_url: AnyHttpUrl | None = Field(default=None)
    mcp_oauth_required_scopes: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
    )
    mcp_oauth_jwt_key: str | None = Field(default=None)
    mcp_oauth_jwks_url: AnyHttpUrl | None = Field(default=None)
    mcp_oauth_jwt_algorithms: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["RS256"],
    )
    mcp_oauth_audience: str | None = Field(default=None)
    mcp_oauth_leeway_seconds: int = Field(default=30, ge=0)
    mcp_oauth_jwks_cache_ttl: int = Field(default=300, ge=0)

    @field_validator("mcp_oauth_required_scopes", "mcp_oauth_jwt_algorithms", mode="before")
    @classmethod
    def normalize_string_list(cls, value: Any, info: ValidationInfo) -> list[str]:
        """Parse comma-separated strings or JSON arrays into list[str]."""
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list):
                    raise ValueError(f"Expected a JSON array for {info.field_name}")
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in stripped.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise ValueError("Expected a comma-separated string or list")

    @model_validator(mode="after")
    def validate_mcp_oauth(self) -> "Settings":
        """Ensure OAuth settings are consistent when enabled."""
        if not self.mcp_oauth_enabled:
            return self
        if self.mcp_transport != "http":
            raise ValueError("MCP_OAUTH_ENABLED requires MCP_TRANSPORT=http")

        required_fields = {
            "MCP_OAUTH_ISSUER_URL": self.mcp_oauth_issuer_url,
            "MCP_OAUTH_RESOURCE_SERVER_URL": self.mcp_oauth_resource_server_url,
        }
        missing = [name for name, value in required_fields.items() if not value]
        if missing:
            raise ValueError(f"MCP OAuth requires: {', '.join(missing)}")

        if not self.mcp_oauth_jwt_algorithms:
            raise ValueError("MCP OAuth requires at least one JWT algorithm")

        if not self.mcp_oauth_jwt_key and not self.mcp_oauth_jwks_url:
            raise ValueError(
                "MCP OAuth requires one of MCP_OAUTH_JWT_KEY (static secret/PEM) "
                "or MCP_OAUTH_JWKS_URL (e.g. Keycloak "
                "/realms/<realm>/protocol/openid-connect/certs)"
            )
        if self.mcp_oauth_jwt_key and self.mcp_oauth_jwks_url:
            raise ValueError(
                "Set only one of MCP_OAUTH_JWT_KEY or MCP_OAUTH_JWKS_URL, not both"
            )

        hmac_algs = {a for a in self.mcp_oauth_jwt_algorithms if a.startswith("HS")}
        if hmac_algs and self.mcp_oauth_jwks_url:
            raise ValueError(
                "HMAC algorithms (HS256/384/512) are incompatible with JWKS. "
                "JWKS is for asymmetric keys (RS*/ES*/PS*). "
                "Either remove HS* from MCP_OAUTH_JWT_ALGORITHMS or "
                "switch to MCP_OAUTH_JWT_KEY."
            )
        if hmac_algs:
            min_bytes = 32
            key_bytes = len((self.mcp_oauth_jwt_key or "").encode("utf-8"))
            if key_bytes < min_bytes:
                raise ValueError(
                    f"MCP_OAUTH_JWT_KEY must be at least {min_bytes} bytes "
                    f"when an HMAC algorithm is used (got {key_bytes}). "
                    "Generate one with: "
                    "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )

        return self

    def validate_litellm_api_key(self) -> None:
        """Raise ValueError if the LiteLLM API key is unset or placeholder."""
        if not self.litellm_api_key or self.litellm_api_key == "sk-placeholder":
            raise ValueError(
                "LITELLM_API_KEY is not configured. Set it in .env or environment."
            )

    def resolved_embedding_model(self) -> str:
        """Return the embedding model name based on the provider setting."""
        if self.embedding_provider == "local":
            return self.local_embedding_model
        return self.litellm_embedding_model

    def resolved_litellm_base_url(self) -> str:
        """Return the LiteLLM base URL, with validation for local models."""
        if self.embedding_provider == "local" and "localhost" not in self.litellm_base_url:
            logger = __import__("logging").getLogger(__name__)
            logger.warning(
                "Local embedding model selected but LITELLM_BASE_URL=%s points to a remote host.",
                self.litellm_base_url,
            )
        return self.litellm_base_url


@lru_cache
def get_settings() -> Settings:
    """Get application settings (cached singleton)."""
    return Settings()
