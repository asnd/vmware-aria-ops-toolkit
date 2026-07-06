"""Application configuration using Pydantic Settings."""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = "NSX-T/AVI API Gateway"
    debug: bool = False
    api_version: str = "v1"

    # Configuration paths
    sites_config_path: Path = Path("config/sites.yml")
    operations_allowlist_path: Path = Path("config/operations_allowlist.yml")

    # JWT Authentication
    jwt_secret_key: str | None = None
    jwt_algorithm: str = "HS256"  # HS256 or RS256
    access_token_expire_minutes: int = 60
    jwt_private_key_path: Path | None = None  # For RS256 signing
    jwt_public_key_path: Path | None = None  # For RS256 verification
    admin_password_hash: str | None = None
    operator_password_hash: str | None = None
    readonly_password_hash: str | None = None

    # Job tracking
    job_retention_minutes: int = 1440  # 24 hours
    job_cleanup_interval_seconds: int = 300  # 5 minutes
    max_concurrent_jobs: int = 50

    # API timeouts (seconds)
    api_connection_timeout: int = 30
    api_operation_timeout: int = 300  # 5 minutes
    api_max_retries: int = 3

    # Idempotency
    idempotency_cache_ttl_seconds: int = 86400  # 24 hours

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text
    audit_log_path: Path = Path("logs/audit.jsonl")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1

    # CORS (optional)
    cors_origins: list[str] = []

    class Config:
        """Pydantic configuration."""

        env_file = ".env"
        env_prefix = "GATEWAY_"

    def validate_production_settings(self) -> list[str]:
        """Validate settings for production deployment."""
        issues = []

        missing_auth_vars = self.get_missing_auth_env_vars()
        if missing_auth_vars:
            issues.append(
                "CRITICAL: Missing required authentication configuration: "
                + ", ".join(missing_auth_vars)
            )

        if self.debug:
            issues.append("WARNING: debug mode is enabled in production")

        if not self.sites_config_path.exists():
            issues.append(
                f"WARNING: sites configuration file not found: {self.sites_config_path}"
            )

        if not self.operations_allowlist_path.exists():
            issues.append(
                f"WARNING: operations allowlist file not found: {self.operations_allowlist_path}"
            )

        return issues

    def get_missing_auth_env_vars(self) -> list[str]:
        """Return required auth-related environment variables that are missing."""
        missing = []

        if self.jwt_algorithm.upper().startswith("HS"):
            if not self.jwt_secret_key:
                missing.append("GATEWAY_JWT_SECRET_KEY")
        elif self.jwt_algorithm.upper().startswith("RS"):
            if self.jwt_private_key_path is None:
                missing.append("GATEWAY_JWT_PRIVATE_KEY_PATH")
            if self.jwt_public_key_path is None:
                missing.append("GATEWAY_JWT_PUBLIC_KEY_PATH")

        auth_hashes = {
            "GATEWAY_ADMIN_PASSWORD_HASH": self.admin_password_hash,
            "GATEWAY_OPERATOR_PASSWORD_HASH": self.operator_password_hash,
            "GATEWAY_READONLY_PASSWORD_HASH": self.readonly_password_hash,
        }
        missing.extend(env_var for env_var, value in auth_hashes.items() if not value)

        return missing

    def require_auth_configuration(self) -> None:
        """Raise a clear error if required auth configuration is missing."""
        missing_auth_vars = self.get_missing_auth_env_vars()
        if missing_auth_vars:
            raise RuntimeError(
                "Authentication is not configured. Set the following environment "
                f"variables: {', '.join(missing_auth_vars)}"
            )


# Global settings instance
settings = Settings()
