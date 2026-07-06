"""OAuth2 authentication with password flow."""

from datetime import timedelta
from typing import Annotated, TypedDict

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext

from app.auth.jwt import create_access_token, decode_access_token
from app.config import settings
from app.models.auth import Token, User


class UserRecord(TypedDict):
    """Configured in-memory user record."""

    username: str
    hashed_password: str
    roles: list[str]
    permissions: list[str]
    disabled: bool


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 password bearer for token extraction
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")

USER_DEFINITIONS = {
    "admin": {
        "roles": ["admin", "operator"],
        "permissions": [
            "nsxt:*",
            "avi:*",
            "jobs:*",
            "sites:*",
        ],
        "password_hash_attr": "admin_password_hash",
        "password_hash_env": "GATEWAY_ADMIN_PASSWORD_HASH",
    },
    "operator": {
        "roles": ["operator"],
        "permissions": [
            "nsxt:segment:create",
            "nsxt:segment:read",
            "nsxt:segment:update",
            "nsxt:tier1_gateway:create",
            "nsxt:tier1_gateway:read",
            "nsxt:nat_rule:*",
            "nsxt:firewall_rule:create",
            "nsxt:firewall_rule:read",
            "avi:virtual_service:create",
            "avi:virtual_service:read",
            "avi:pool:*",
            "avi:vip:*",
            "jobs:read",
            "sites:read",
        ],
        "password_hash_attr": "operator_password_hash",
        "password_hash_env": "GATEWAY_OPERATOR_PASSWORD_HASH",
    },
    "readonly": {
        "roles": ["readonly"],
        "permissions": [
            "nsxt:*:read",
            "avi:*:read",
            "jobs:read",
            "sites:read",
        ],
        "password_hash_attr": "readonly_password_hash",
        "password_hash_env": "GATEWAY_READONLY_PASSWORD_HASH",
    },
}


def get_users_db() -> dict[str, UserRecord]:
    """Load users from explicit environment-backed configuration."""
    users: dict[str, UserRecord] = {}
    missing_hashes: list[str] = []

    for username, definition in USER_DEFINITIONS.items():
        password_hash = getattr(settings, definition["password_hash_attr"])
        if not password_hash:
            missing_hashes.append(definition["password_hash_env"])
            continue

        users[username] = UserRecord(
            username=username,
            hashed_password=password_hash,
            roles=list(definition["roles"]),
            permissions=list(definition["permissions"]),
            disabled=False,
        )

    if missing_hashes:
        raise RuntimeError(
            "Authentication is not configured. Set the following environment "
            f"variables: {', '.join(missing_hashes)}"
        )

    return users


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def authenticate_user(username: str, password: str) -> User | None:
    """
    Authenticate a user with username and password.

    Args:
        username: Username
        password: Plain text password

    Returns:
        User object if authentication successful, None otherwise
    """
    user_dict = get_users_db().get(username)
    if not user_dict:
        return None

    if not verify_password(password, user_dict["hashed_password"]):
        return None

    return User(
        username=user_dict["username"],
        roles=user_dict["roles"],
        permissions=user_dict["permissions"],
        disabled=user_dict["disabled"],
    )


def create_user_token(user: User) -> Token:
    """
    Create an access token for a user.

    Args:
        user: User object

    Returns:
        Token object with access token
    """
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)

    token_data = {
        "sub": user.username,
        "roles": user.roles,
        "permissions": user.permissions,
    }

    access_token = create_access_token(
        data=token_data, expires_delta=access_token_expires
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,  # Convert to seconds
    )


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    Get the current authenticated user from JWT token.

    Args:
        token: JWT token from Authorization header

    Returns:
        User object

    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token_data = decode_access_token(token)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if token_data is None:
        raise credentials_exception

    # Get user from database
    try:
        user_dict = get_users_db().get(token_data.username)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if user_dict is None:
        raise credentials_exception

    user = User(
        username=user_dict["username"],
        roles=user_dict["roles"],
        permissions=user_dict["permissions"],
        disabled=user_dict["disabled"],
    )

    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled"
        )

    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    Get the current active (non-disabled) user.

    Args:
        current_user: Current user from get_current_user

    Returns:
        User object

    Raises:
        HTTPException: If user is disabled
    """
    if current_user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user"
        )
    return current_user
