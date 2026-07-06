"""Unit tests for site inventory parser."""


from app.core.inventory import SiteInventory


class TestSiteInventory:
    """Test suite for SiteInventory class."""

    def test_load_sites(self, temp_sites_config):
        """Test loading sites from YAML file."""
        inventory = SiteInventory(temp_sites_config)
        inventory.load()

        sites = inventory.get_sites()
        assert len(sites) == 2

        site1 = sites[0]
        assert site1.site_id == "test-site-1"
        assert site1.name == "Test Site 1"
        assert site1.region == "us-east"

    def test_get_site_by_id(self, temp_sites_config):
        """Test retrieving site by ID."""
        inventory = SiteInventory(temp_sites_config)
        inventory.load()

        site = inventory.get_site("test-site-1")
        assert site is not None
        assert site.site_id == "test-site-1"
        assert site.name == "Test Site 1"

    def test_get_site_not_found(self, temp_sites_config):
        """Test retrieving non-existent site."""
        inventory = SiteInventory(temp_sites_config)
        inventory.load()

        site = inventory.get_site("non-existent")
        assert site is None

    def test_site_has_nsxt(self, temp_sites_config):
        """Test checking if site has NSX-T configured."""
        inventory = SiteInventory(temp_sites_config)
        inventory.load()

        site1 = inventory.get_site("test-site-1")
        assert site1.has_nsxt() is True

        site2 = inventory.get_site("test-site-2")
        assert site2.has_nsxt() is True

    def test_site_has_avi(self, temp_sites_config):
        """Test checking if site has AVI configured."""
        inventory = SiteInventory(temp_sites_config)
        inventory.load()

        site1 = inventory.get_site("test-site-1")
        assert site1.has_avi() is True

        site2 = inventory.get_site("test-site-2")
        assert site2.has_avi() is False

    def test_filter_sites_by_tag(self, temp_sites_config):
        """Test filtering sites by tags."""
        inventory = SiteInventory(temp_sites_config)
        inventory.load()

        # Filter by environment
        test_sites = inventory.get_sites(filters={"environment": "test"})
        assert len(test_sites) == 2

        # Filter by tier
        bronze_sites = inventory.get_sites(filters={"tier": "bronze"})
        assert len(bronze_sites) == 1
        assert bronze_sites[0].site_id == "test-site-1"

    def test_reload_inventory(self, temp_sites_config):
        """Test reloading inventory."""
        inventory = SiteInventory(temp_sites_config)
        inventory.load()

        assert inventory.get_site_count() == 2

        # Reload should work without error
        inventory.reload()
        assert inventory.get_site_count() == 2

    def test_nsxt_endpoint_properties(self, temp_sites_config):
        """Test NSX-T endpoint properties."""
        inventory = SiteInventory(temp_sites_config)
        inventory.load()

        site = inventory.get_site("test-site-1")
        assert site.nsxt is not None
        assert site.nsxt.manager_url == "https://nsxt-test1.example.com"
        assert site.nsxt.username == "test-user"
        assert site.nsxt.verify_ssl is False

    def test_avi_endpoint_properties(self, temp_sites_config):
        """Test AVI endpoint properties."""
        inventory = SiteInventory(temp_sites_config)
        inventory.load()

        site = inventory.get_site("test-site-1")
        assert site.avi is not None
        assert site.avi.controller_url == "https://avi-test1.example.com"
        assert site.avi.tenant == "admin"
        assert site.avi.api_version == "22.1.3"
