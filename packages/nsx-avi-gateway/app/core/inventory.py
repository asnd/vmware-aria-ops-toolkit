"""Site inventory parser for NSX-T and AVI Load Balancer endpoints."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.config import settings


@dataclass
class NSXTEndpoint:
    """NSX-T Manager endpoint configuration."""

    manager_url: str
    username: str
    password: str
    verify_ssl: bool = True
    cert_path: Path | None = None


@dataclass
class AVIEndpoint:
    """AVI Controller endpoint configuration."""

    controller_url: str
    username: str
    password: str
    tenant: str = "admin"
    api_version: str = "22.1.3"
    verify_ssl: bool = True


@dataclass
class Site:
    """Represents a site with NSX-T and/or AVI endpoints."""

    site_id: str
    name: str
    region: str
    nsxt: NSXTEndpoint | None = None
    avi: AVIEndpoint | None = None
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        """Get display name for UI."""
        return f"{self.name} ({self.site_id})"

    def has_nsxt(self) -> bool:
        """Check if site has NSX-T configured."""
        return self.nsxt is not None

    def has_avi(self) -> bool:
        """Check if site has AVI configured."""
        return self.avi is not None


class SiteInventory:
    """Parse and manage site inventory from YAML configuration."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or settings.sites_config_path
        self._sites: dict[str, Site] = {}
        self._loaded = False

    def load(self) -> None:
        """Load and parse the inventory file."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Sites configuration file not found: {self.config_path}"
            )

        with open(self.config_path) as f:
            data = yaml.safe_load(f)

        self._parse_inventory(data)
        self._loaded = True

    def _parse_inventory(self, data: dict[str, Any]) -> None:
        """Parse inventory data structure."""
        if not data or "sites" not in data:
            raise ValueError("Invalid inventory format: missing 'sites' key")

        sites_list = data["sites"]
        if not isinstance(sites_list, list):
            raise ValueError("Invalid inventory format: 'sites' must be a list")

        for site_data in sites_list:
            site = self._parse_site(site_data)
            if site:
                self._sites[site.site_id] = site

    def _parse_site(self, site_data: dict[str, Any]) -> Site | None:
        """Parse a single site from inventory."""
        if not isinstance(site_data, dict):
            return None

        # Required fields
        site_id = site_data.get("site_id")
        name = site_data.get("name")
        region = site_data.get("region", "unknown")

        if not site_id or not name:
            return None

        # Parse NSX-T endpoint
        nsxt_endpoint = None
        if "nsxt" in site_data and site_data["nsxt"]:
            nsxt_data = site_data["nsxt"]
            nsxt_endpoint = NSXTEndpoint(
                manager_url=self._resolve_variable(nsxt_data.get("manager_url", "")),
                username=self._resolve_variable(nsxt_data.get("username", "")),
                password=self._resolve_variable(nsxt_data.get("password", "")),
                verify_ssl=nsxt_data.get("verify_ssl", True),
                cert_path=(
                    Path(nsxt_data["cert_path"])
                    if "cert_path" in nsxt_data
                    else None
                ),
            )

        # Parse AVI endpoint
        avi_endpoint = None
        if "avi" in site_data and site_data["avi"]:
            avi_data = site_data["avi"]
            avi_endpoint = AVIEndpoint(
                controller_url=self._resolve_variable(
                    avi_data.get("controller_url", "")
                ),
                username=self._resolve_variable(avi_data.get("username", "")),
                password=self._resolve_variable(avi_data.get("password", "")),
                tenant=avi_data.get("tenant", "admin"),
                api_version=avi_data.get("api_version", "22.1.3"),
                verify_ssl=avi_data.get("verify_ssl", True),
            )

        # Parse tags
        tags = site_data.get("tags", {})
        if not isinstance(tags, dict):
            tags = {}

        return Site(
            site_id=site_id,
            name=name,
            region=region,
            nsxt=nsxt_endpoint,
            avi=avi_endpoint,
            tags=tags,
        )

    def _resolve_variable(self, value: str) -> str:
        """
        Resolve variable references in configuration.

        Supports:
        - ${ENV:VAR_NAME} - environment variable
        - ${VAULT:path/to/secret} - Vault path (placeholder for future integration)
        """
        if not isinstance(value, str):
            return value

        # Environment variable: ${ENV:VAR_NAME}
        env_pattern = r"\$\{ENV:([^}]+)\}"
        match = re.search(env_pattern, value)
        if match:
            import os

            env_var = match.group(1)
            env_value = os.getenv(env_var, "")
            return re.sub(env_pattern, env_value, value)

        # Vault placeholder: ${VAULT:path} - for future implementation
        vault_pattern = r"\$\{VAULT:([^}]+)\}"
        if re.search(vault_pattern, value):
            # For now, just return as-is (implement Vault integration later)
            # In production, this would fetch from Vault
            return value

        return value

    def get_sites(self, filters: dict[str, str] | None = None) -> list[Site]:
        """
        Get all sites, optionally filtered by tags.

        Args:
            filters: Dictionary of tag filters (e.g., {"environment": "production"})

        Returns:
            List of Site objects matching filters
        """
        if not self._loaded:
            self.load()

        sites = list(self._sites.values())

        if filters:
            filtered_sites = []
            for site in sites:
                match = all(
                    site.tags.get(key) == value for key, value in filters.items()
                )
                if match:
                    filtered_sites.append(site)
            return filtered_sites

        return sites

    def get_site(self, site_id: str) -> Site | None:
        """Get site by ID."""
        if not self._loaded:
            self.load()
        return self._sites.get(site_id)

    def reload(self) -> None:
        """Reload inventory from file."""
        self._sites.clear()
        self._loaded = False
        self.load()

    def get_site_count(self) -> int:
        """Get total number of sites."""
        if not self._loaded:
            self.load()
        return len(self._sites)


# Global inventory instance
_inventory: SiteInventory | None = None


def get_inventory() -> SiteInventory:
    """Get the global site inventory instance."""
    global _inventory
    if _inventory is None:
        _inventory = SiteInventory()
    return _inventory


def reload_inventory() -> SiteInventory:
    """Reload and return the inventory."""
    global _inventory
    if _inventory is None:
        _inventory = SiteInventory()
    _inventory.reload()
    return _inventory
