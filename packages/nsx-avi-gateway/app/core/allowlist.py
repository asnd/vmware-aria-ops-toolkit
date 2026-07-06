"""Operations allowlist validator for preventing disruptive actions."""

import fnmatch
import logging
from pathlib import Path
from typing import Any

import yaml

from app.config import settings

logger = logging.getLogger(__name__)


class OperationAllowlist:
    """Validate operations against allowlist configuration."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or settings.operations_allowlist_path
        self._config: dict[str, Any] = {}
        self._loaded = False

    def load(self) -> None:
        """Load allowlist configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Operations allowlist file not found: {self.config_path}"
            )

        with open(self.config_path) as f:
            self._config = yaml.safe_load(f)

        self._loaded = True
        logger.info(f"Loaded operations allowlist from {self.config_path}")

    def is_allowed(
        self,
        operation: str,
        user_role: str,
        site_id: str | None = None,
    ) -> bool:
        """
        Check if an operation is allowed.

        Args:
            operation: Operation string (e.g., "nsxt.segment.create")
            user_role: User's role (e.g., "admin", "operator")
            site_id: Optional site ID for site-specific rules

        Returns:
            True if operation is allowed, False otherwise
        """
        if not self._loaded:
            self.load()

        # Parse operation: "nsxt.segment.create" -> ("nsxt", "segment", "create")
        parts = operation.split(".")
        if len(parts) != 3:
            logger.warning(f"Invalid operation format: {operation}")
            return False

        platform, resource, action = parts

        # Check role-based overrides
        if self._is_allowed_by_role(operation, user_role):
            logger.debug(
                f"Operation allowed by role override ({user_role}): {operation}"
            )
            return True

        # Check if explicitly blocked
        if self._is_blocked(operation, platform):
            logger.warning(f"Operation blocked by allowlist: {operation}")
            return False

        # Check if allowed in base configuration
        if self._is_allowed_in_base(platform, resource, action):
            logger.debug(f"Operation allowed by base config: {operation}")
            return True

        # Default deny
        logger.warning(f"Operation not allowed (default deny): {operation}")
        return False

    def _is_blocked(self, operation: str, platform: str) -> bool:
        """Check if operation is explicitly blocked."""
        if platform not in self._config:
            return False

        blocked_list = self._config[platform].get("blocked", [])

        for blocked_pattern in blocked_list:
            # Support wildcards: "tier0_gateways.*" blocks all T0 operations
            normalized_pattern = (
                blocked_pattern
                if blocked_pattern.startswith(f"{platform}.")
                else f"{platform}.{blocked_pattern}"
            )
            if fnmatch.fnmatch(operation, normalized_pattern):
                return True

        return False

    def _is_allowed_in_base(self, platform: str, resource: str, action: str) -> bool:
        """Check if operation is allowed in base configuration."""
        if platform not in self._config:
            return False

        platform_config = self._config[platform]

        # Check resource-specific actions
        if resource not in platform_config:
            return False

        allowed_actions = platform_config[resource]
        if not isinstance(allowed_actions, list):
            return False

        return action in allowed_actions

    def _is_allowed_by_role(self, operation: str, user_role: str) -> bool:
        """Check if operation is allowed by role-based override."""
        role_overrides = self._config.get("role_overrides", {})

        if user_role not in role_overrides:
            return False

        role_config = role_overrides[user_role]

        # Check additional permissions
        additional_perms = role_config.get("additional_permissions", [])
        for perm in additional_perms:
            # Support wildcards
            if fnmatch.fnmatch(operation, perm):
                return True

        # Check allowed operations (for readonly role)
        allowed_ops = role_config.get("allowed_operations", [])
        for allowed_pattern in allowed_ops:
            if fnmatch.fnmatch(operation, allowed_pattern):
                return True

        return False

    def get_blocked_reason(self, operation: str) -> str:
        """
        Get human-readable reason why an operation is blocked.

        Args:
            operation: Operation string

        Returns:
            Reason string
        """
        parts = operation.split(".")
        if len(parts) != 3:
            return "Invalid operation format"

        platform, resource, action = parts

        # Check if explicitly blocked
        if platform in self._config:
            blocked_list = self._config[platform].get("blocked", [])
            for blocked_pattern in blocked_list:
                normalized_pattern = (
                    blocked_pattern
                    if blocked_pattern.startswith(f"{platform}.")
                    else f"{platform}.{blocked_pattern}"
                )
                if fnmatch.fnmatch(operation, normalized_pattern):
                    return f"Explicitly blocked: {normalized_pattern}"

        # Check if resource exists but action not allowed
        if platform in self._config and resource in self._config[platform]:
            allowed_actions = self._config[platform][resource]
            if isinstance(allowed_actions, list) and action not in allowed_actions:
                return f"Action '{action}' not in allowlist for {platform}.{resource}"

        # Default
        return "Operation not in allowlist (default deny)"

    def get_allowed_operations(
        self, platform: str | None = None, user_role: str | None = None
    ) -> list[str]:
        """
        Get list of allowed operations.

        Args:
            platform: Optional platform filter ("nsxt" or "avi")
            user_role: Optional role to include role-based overrides

        Returns:
            List of allowed operation strings
        """
        if not self._loaded:
            self.load()

        allowed_ops = []

        # Get base allowed operations
        platforms = [platform] if platform else ["nsxt", "avi"]

        for plat in platforms:
            if plat not in self._config:
                continue

            plat_config = self._config[plat]
            for resource, actions in plat_config.items():
                if resource == "blocked":
                    continue

                if isinstance(actions, list):
                    for action in actions:
                        op = f"{plat}.{resource}.{action}"
                        if not self._is_blocked(op, plat):
                            allowed_ops.append(op)

        # Add role-based permissions
        if user_role:
            role_overrides = self._config.get("role_overrides", {})
            if user_role in role_overrides:
                additional_perms = role_overrides[user_role].get(
                    "additional_permissions", []
                )
                allowed_ops.extend(additional_perms)

        return sorted(set(allowed_ops))

    def reload(self) -> None:
        """Reload allowlist configuration from file."""
        self._config.clear()
        self._loaded = False
        self.load()


# Global allowlist instance
_allowlist: OperationAllowlist | None = None


def get_allowlist() -> OperationAllowlist:
    """Get the global allowlist instance."""
    global _allowlist
    if _allowlist is None:
        _allowlist = OperationAllowlist()
    return _allowlist


def reload_allowlist() -> OperationAllowlist:
    """Reload and return the allowlist."""
    global _allowlist
    if _allowlist is None:
        _allowlist = OperationAllowlist()
    _allowlist.reload()
    return _allowlist
