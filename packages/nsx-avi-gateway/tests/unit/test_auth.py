"""Unit tests for authentication."""

import pytest

from app.auth.jwt import create_access_token, decode_access_token
from app.auth.oauth2 import authenticate_user, get_password_hash, verify_password
from app.auth.rbac import RBACChecker


class TestJWT:
    """Test suite for JWT functionality."""

    def test_create_access_token(self):
        """Test creating JWT access token."""
        data = {
            "sub": "test-user",
            "roles": ["operator"],
            "permissions": ["nsxt:segment:create"],
        }

        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_access_token(self):
        """Test decoding JWT access token."""
        data = {
            "sub": "test-user",
            "roles": ["operator"],
            "permissions": ["nsxt:segment:create"],
        }

        token = create_access_token(data)
        decoded = decode_access_token(token)

        assert decoded is not None
        assert decoded.username == "test-user"
        assert "operator" in decoded.roles
        assert "nsxt:segment:create" in decoded.permissions

    def test_decode_invalid_token(self):
        """Test decoding invalid token."""
        invalid_token = "invalid.token.here"

        decoded = decode_access_token(invalid_token)
        assert decoded is None


class TestOAuth2:
    """Test suite for OAuth2 functionality."""

    def test_verify_password_correct(self, auth_test_password):
        """Test password verification with correct password."""
        hashed = get_password_hash(auth_test_password)

        result = verify_password(auth_test_password, hashed)
        assert result is True

    def test_verify_password_incorrect(self, auth_test_password):
        """Test password verification with incorrect password."""
        hashed = get_password_hash(auth_test_password)

        result = verify_password("wrong-password", hashed)
        assert result is False

    def test_authenticate_user_success(self, auth_test_password):
        """Test successful user authentication."""
        user = authenticate_user("admin", auth_test_password)

        assert user is not None
        assert user.username == "admin"
        assert "admin" in user.roles

    def test_authenticate_user_wrong_password(self):
        """Test authentication with wrong password."""
        user = authenticate_user("admin", "wrong-password")
        assert user is None

    def test_authenticate_user_not_found(self, auth_test_password):
        """Test authentication with non-existent user."""
        user = authenticate_user("non-existent", auth_test_password)
        assert user is None

    def test_authenticate_user_requires_explicit_configuration(self, monkeypatch):
        """Test that auth fails clearly when password hashes are missing."""
        from app.config import settings

        monkeypatch.setattr(settings, "admin_password_hash", None)

        with pytest.raises(RuntimeError, match="GATEWAY_ADMIN_PASSWORD_HASH"):
            authenticate_user("admin", "irrelevant")


class TestRBAC:
    """Test suite for RBAC functionality."""

    def test_permission_exact_match(self, test_user_operator):
        """Test exact permission match."""
        checker = RBACChecker("nsxt:segment:create")

        has_perm = checker._user_has_permission(
            test_user_operator, "nsxt:segment:create"
        )
        assert has_perm is True

    def test_permission_wildcard_match(self, test_user_admin):
        """Test wildcard permission match."""
        checker = RBACChecker("nsxt:segment:create")

        # Admin has nsxt:* which should match nsxt:segment:create
        has_perm = checker._user_has_permission(test_user_admin, "nsxt:segment:create")
        assert has_perm is True

    def test_permission_denied(self, test_user_readonly):
        """Test permission denied."""
        checker = RBACChecker("nsxt:segment:create")

        # Readonly user doesn't have create permission
        has_perm = checker._user_has_permission(
            test_user_readonly, "nsxt:segment:create"
        )
        assert has_perm is False

    def test_permission_wildcard_matching_patterns(self, test_user_operator):
        """Test various wildcard matching patterns."""
        # test_user_operator has "avi:pool:*"

        checker1 = RBACChecker("avi:pool:create")
        assert (
            checker1._user_has_permission(test_user_operator, "avi:pool:create") is True
        )

        checker2 = RBACChecker("avi:pool:delete")
        assert (
            checker2._user_has_permission(test_user_operator, "avi:pool:delete") is True
        )

        # But not for other resources
        checker3 = RBACChecker("avi:vip:create")
        assert (
            checker3._user_has_permission(test_user_operator, "avi:vip:create") is False
        )
