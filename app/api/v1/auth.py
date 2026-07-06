"""Authentication API endpoints."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.jwt import get_token_expiration
from app.auth.oauth2 import (
    authenticate_user,
    create_user_token,
    get_current_active_user,
    oauth2_scheme,
)
from app.core.audit_log import get_audit_logger
from app.models.auth import Token, User, UserInfo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/token", response_model=Token)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    """
    OAuth2 password flow - obtain access token.

    Returns JWT access token for authenticated user.
    """
    audit_logger = get_audit_logger()

    # Authenticate user
    try:
        user = authenticate_user(form_data.username, form_data.password)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if not user:
        # Log failed authentication
        await audit_logger.log_authentication(
            username=form_data.username,
            success=False,
            error="Invalid credentials",
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Log successful authentication
    await audit_logger.log_authentication(
        username=user.username,
        success=True,
    )

    # Create access token
    try:
        token = create_user_token(user)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    logger.info(f"User {user.username} authenticated successfully")

    return token


@router.get("/me", response_model=UserInfo)
async def get_current_user_info(
    current_user: Annotated[User, Depends(get_current_active_user)],
    token: Annotated[str, Depends(oauth2_scheme)],
):
    """
    Get current user information.

    Returns user details including roles and permissions.
    """
    # Get token expiration
    expires_at = get_token_expiration(token)

    return UserInfo(
        username=current_user.username,
        roles=current_user.roles,
        permissions=current_user.permissions,
        token_expires_at=expires_at,
    )
