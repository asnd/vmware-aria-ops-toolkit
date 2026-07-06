"""Role-Based Access Control (RBAC) for API endpoints."""

import fnmatch
from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.auth.oauth2 import get_current_active_user
from app.models.auth import User


class RBACChecker:
    """
    Dependency for checking if user has required permission.

    Usage:
        @router.post("/nsxt/{site_id}/segments")
        async def create_segment(
            user: User = Depends(RBACChecker("nsxt:segment:create"))
        ):
            ...
    """

    def __init__(self, required_permission: str):
        """
        Initialize RBAC checker.

        Args:
            required_permission: Permission string (e.g., "nsxt:segment:create")
        """
        self.required_permission = required_permission

    async def __call__(self, user: User = Depends(get_current_active_user)) -> User:
        """
        Check if user has required permission.

        Args:
            user: Current authenticated user

        Returns:
            User object if permission granted

        Raises:
            HTTPException: If permission denied
        """
        if not self._user_has_permission(user, self.required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {self.required_permission}",
            )
        return user

    def _user_has_permission(self, user: User, required_permission: str) -> bool:
        """
        Check if user has a specific permission (supports wildcards).

        Args:
            user: User object
            required_permission: Required permission string

        Returns:
            True if user has permission, False otherwise
        """
        # Check for exact match
        if required_permission in user.permissions:
            return True

        # Check for wildcard matches
        for user_perm in user.permissions:
            if self._permission_matches(user_perm, required_permission):
                return True

        return False

    @staticmethod
    def _permission_matches(user_perm: str, required_perm: str) -> bool:
        """
        Check if a user permission (with wildcards) matches required permission.

        Examples:
            nsxt:* matches nsxt:segment:create
            nsxt:segment:* matches nsxt:segment:create
            avi:*:read matches avi:pool:read

        Args:
            user_perm: User's permission (may contain wildcards)
            required_perm: Required permission (no wildcards)

        Returns:
            True if user permission matches required permission
        """
        return fnmatch.fnmatch(required_perm, user_perm)


class RoleChecker:
    """
    Dependency for checking if user has required role.

    Usage:
        @router.delete("/api/v1/jobs/{job_id}")
        async def cancel_job(
            user: User = Depends(RoleChecker("admin"))
        ):
            ...
    """

    def __init__(self, required_role: str):
        """
        Initialize role checker.

        Args:
            required_role: Required role name
        """
        self.required_role = required_role

    async def __call__(self, user: User = Depends(get_current_active_user)) -> User:
        """
        Check if user has required role.

        Args:
            user: Current authenticated user

        Returns:
            User object if role check passes

        Raises:
            HTTPException: If user doesn't have required role
        """
        if not user.has_role(self.required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role required: {self.required_role}",
            )
        return user


def require_permission(permission: str) -> Callable:
    """
    Factory function for creating permission checkers.

    Args:
        permission: Required permission string

    Returns:
        RBAC checker dependency

    Example:
        @router.get("/protected")
        async def protected_route(
            user: User = Depends(require_permission("nsxt:segment:read"))
        ):
            ...
    """
    return RBACChecker(permission)


def require_role(role: str) -> Callable:
    """
    Factory function for creating role checkers.

    Args:
        role: Required role name

    Returns:
        Role checker dependency

    Example:
        @router.post("/admin/reload")
        async def reload_config(
            user: User = Depends(require_role("admin"))
        ):
            ...
    """
    return RoleChecker(role)


# Common permission checker instances for convenience
AdminOnly = RoleChecker("admin")
OperatorOrAdmin = Depends(get_current_active_user)  # All authenticated users
