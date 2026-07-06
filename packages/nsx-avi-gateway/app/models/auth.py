"""Authentication and authorization models."""

from datetime import datetime

from pydantic import BaseModel, Field


class Token(BaseModel):
    """OAuth2 token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenData(BaseModel):
    """Data stored in JWT token."""

    username: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class User(BaseModel):
    """User model with roles and permissions."""

    username: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    disabled: bool = False

    @property
    def primary_role(self) -> str:
        """Get the primary (first) role."""
        return self.roles[0] if self.roles else "operator"

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles


class LoginRequest(BaseModel):
    """Login request for OAuth2 password flow."""

    username: str
    password: str


class UserInfo(BaseModel):
    """User information response."""

    username: str
    roles: list[str]
    permissions: list[str]
    token_expires_at: datetime | None = None
