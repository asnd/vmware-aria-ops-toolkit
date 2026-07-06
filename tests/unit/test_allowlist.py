"""Unit tests for operations allowlist."""


from app.core.allowlist import OperationAllowlist


class TestOperationAllowlist:
    """Test suite for OperationAllowlist class."""

    def test_load_allowlist(self, temp_allowlist_config):
        """Test loading allowlist configuration."""
        allowlist = OperationAllowlist(temp_allowlist_config)
        allowlist.load()

        # Should load without error
        assert allowlist._loaded is True

    def test_allowed_operation(self, temp_allowlist_config):
        """Test checking allowed operation."""
        allowlist = OperationAllowlist(temp_allowlist_config)
        allowlist.load()

        # Segment create is allowed for operator
        assert allowlist.is_allowed("nsxt.segments.create", "operator") is True

        # Pool delete is allowed for operator
        assert allowlist.is_allowed("avi.pools.delete", "operator") is True

    def test_blocked_operation(self, temp_allowlist_config):
        """Test checking blocked operation."""
        allowlist = OperationAllowlist(temp_allowlist_config)
        allowlist.load()

        # Segment delete is explicitly blocked
        assert allowlist.is_allowed("nsxt.segments.delete", "operator") is False

        # T0 operations are blocked
        assert allowlist.is_allowed("nsxt.tier0_gateways.create", "operator") is False

    def test_admin_override(self, temp_allowlist_config):
        """Test admin role override."""
        allowlist = OperationAllowlist(temp_allowlist_config)
        allowlist.load()

        # Segment delete blocked for operator
        assert allowlist.is_allowed("nsxt.segments.delete", "operator") is False

        # But allowed for admin via role override
        assert allowlist.is_allowed("nsxt.segments.delete", "admin") is True

    def test_operation_not_in_allowlist(self, temp_allowlist_config):
        """Test operation not in allowlist (default deny)."""
        allowlist = OperationAllowlist(temp_allowlist_config)
        allowlist.load()

        # Operation not listed should be denied
        assert allowlist.is_allowed("nsxt.dhcp_servers.create", "operator") is False

    def test_get_blocked_reason(self, temp_allowlist_config):
        """Test getting reason for blocked operation."""
        allowlist = OperationAllowlist(temp_allowlist_config)
        allowlist.load()

        reason = allowlist.get_blocked_reason("nsxt.segments.delete")
        assert "blocked" in reason.lower()

    def test_get_allowed_operations(self, temp_allowlist_config):
        """Test getting list of allowed operations."""
        allowlist = OperationAllowlist(temp_allowlist_config)
        allowlist.load()

        # Get all NSX-T operations
        nsxt_ops = allowlist.get_allowed_operations(platform="nsxt")
        assert "nsxt.segments.create" in nsxt_ops
        assert "nsxt.segments.read" in nsxt_ops
        assert "nsxt.segments.update" in nsxt_ops

        # Get all AVI operations
        avi_ops = allowlist.get_allowed_operations(platform="avi")
        assert "avi.pools.delete" in avi_ops

    def test_wildcard_blocking(self, temp_allowlist_config):
        """Test wildcard pattern blocking."""
        allowlist = OperationAllowlist(temp_allowlist_config)
        allowlist.load()

        # tier0_gateways.* blocks all T0 operations
        assert allowlist.is_allowed("nsxt.tier0_gateways.create", "operator") is False
        assert allowlist.is_allowed("nsxt.tier0_gateways.read", "operator") is False
        assert allowlist.is_allowed("nsxt.tier0_gateways.update", "operator") is False
