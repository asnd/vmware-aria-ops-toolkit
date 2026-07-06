"""JWT token creation and validation."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt

from app.config import settings
from app.models.auth import TokenData


def _read_key_file(path: Path, env_var_name: str) -> str:
    """Read a configured JWT key file."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"JWT key file configured by {env_var_name} was not found: {path}"
        ) from exc


def _get_signing_key() -> str:
    """Return the configured key used to sign JWTs."""
    algorithm = settings.jwt_algorithm.upper()
    if algorithm.startswith("HS"):
        if not settings.jwt_secret_key:
            raise RuntimeError(
                "JWT signing is not configured. Set GATEWAY_JWT_SECRET_KEY."
            )
        return settings.jwt_secret_key

    if algorithm.startswith("RS"):
        if settings.jwt_private_key_path is None:
            raise RuntimeError(
                "JWT signing is not configured. Set GATEWAY_JWT_PRIVATE_KEY_PATH."
            )
        return _read_key_file(
            settings.jwt_private_key_path,
            "GATEWAY_JWT_PRIVATE_KEY_PATH",
        )

    raise RuntimeError(
        f"Unsupported JWT algorithm configured: {settings.jwt_algorithm}"
    )


def _get_verification_key() -> str:
    """Return the configured key used to verify JWTs."""
    algorithm = settings.jwt_algorithm.upper()
    if algorithm.startswith("HS"):
        return _get_signing_key()

    if algorithm.startswith("RS"):
        if settings.jwt_public_key_path is None:
            raise RuntimeError(
                "JWT verification is not configured. Set GATEWAY_JWT_PUBLIC_KEY_PATH."
            )
        return _read_key_file(
            settings.jwt_public_key_path,
            "GATEWAY_JWT_PUBLIC_KEY_PATH",
        )

    raise RuntimeError(
        f"Unsupported JWT algorithm configured: {settings.jwt_algorithm}"
    )


def _decode_token(token: str, *, verify_exp: bool) -> dict[str, Any] | None:
    """Decode a JWT token with the configured verification key."""
    try:
        return jwt.decode(
            token,
            _get_verification_key(),
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": verify_exp},
        )
    except jwt.InvalidTokenError:
        return None


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Create a JWT access token.

    Args:
        data: Dictionary of claims to encode in the token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(UTC),
        }
    )

    encoded_jwt = jwt.encode(
        to_encode,
        _get_signing_key(),
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt


def decode_access_token(token: str) -> TokenData | None:
    """
    Decode and validate a JWT access token.

    Args:
        token: JWT token string

    Returns:
        TokenData object if valid, None if invalid
    """
    payload = _decode_token(token, verify_exp=True)
    if payload is None:
        return None

    username = payload.get("sub")
    if not isinstance(username, str):
        return None

    roles = payload.get("roles", [])
    permissions = payload.get("permissions", [])

    return TokenData(
        username=username,
        roles=[str(role) for role in roles] if isinstance(roles, list) else [],
        permissions=(
            [str(permission) for permission in permissions]
            if isinstance(permissions, list)
            else []
        ),
    )


def get_token_expiration(token: str) -> datetime | None:
    """
    Get the expiration time of a token.

    Args:
        token: JWT token string

    Returns:
        Expiration datetime if valid, None if invalid
    """
    payload = _decode_token(token, verify_exp=False)
    if payload is None:
        return None

    exp_timestamp = payload.get("exp")
    if isinstance(exp_timestamp, (int, float)):
        return datetime.fromtimestamp(exp_timestamp, tz=UTC)

    return None
