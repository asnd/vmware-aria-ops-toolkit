"""NSX-T Policy API client backed by raw httpx requests."""

import logging
from typing import Any

import httpx

from app.clients.base_client import BaseClient
from app.core.inventory import NSXTEndpoint

logger = logging.getLogger(__name__)


class NSXTClient(BaseClient):
    """NSX-T Policy API client."""

    def __init__(self, endpoint: NSXTEndpoint):
        super().__init__("NSX-T")
        self.endpoint = endpoint
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Initialize the HTTP client used for NSX-T Policy API requests."""
        if self._client is not None:
            return

        logger.info(f"Connecting to NSX-T Manager: {self.endpoint.manager_url}")
        verify: bool | str = self.endpoint.verify_ssl
        if self.endpoint.cert_path is not None:
            verify = str(self.endpoint.cert_path)

        self._client = httpx.AsyncClient(
            base_url=self.endpoint.manager_url.rstrip("/"),
            auth=httpx.BasicAuth(self.endpoint.username, self.endpoint.password),
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(
                self.operation_timeout,
                connect=self.connection_timeout,
            ),
            verify=verify,
        )

    async def disconnect(self) -> None:
        """Close the underlying HTTP client."""
        logger.info("Disconnecting from NSX-T Manager")
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a Policy API request and return the decoded JSON payload."""
        await self.connect()
        client = self._client
        if client is None:
            raise RuntimeError("NSX-T client is not connected")

        async def _send() -> dict[str, Any]:
            response = await client.request(method, path, json=json)
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

        return await self.execute_with_retry(_send)

    @staticmethod
    def _segment_path(segment_id: str) -> str:
        return f"/policy/api/v1/infra/segments/{segment_id}"

    @staticmethod
    def _first_vlan(vlan_ids: list[Any] | None) -> int | None:
        if not vlan_ids:
            return None
        first_vlan = vlan_ids[0]
        if isinstance(first_vlan, int):
            return first_vlan
        if isinstance(first_vlan, str) and first_vlan.isdigit():
            return int(first_vlan)
        return None

    @staticmethod
    def _subnet_gateways(subnets: list[dict[str, Any]] | None) -> list[str]:
        if not subnets:
            return []
        gateways = []
        for subnet in subnets:
            gateway = subnet.get("gateway_address")
            if isinstance(gateway, str):
                gateways.append(gateway)
        return gateways

    async def create_segment(
        self,
        name: str,
        tier1_gateway: str,
        subnets: list[str],
        vlan: int | None = None,
        tags: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Create an NSX-T segment."""
        payload: dict[str, Any] = {
            "display_name": name,
            "tier1_path": tier1_gateway,
            "subnets": [{"gateway_address": subnet} for subnet in subnets],
            "tags": tags or [],
        }
        if vlan is not None:
            payload["vlan_ids"] = [vlan]

        logger.info(f"Creating NSX-T segment: {name}")
        response = await self._request("PUT", self._segment_path(name), json=payload)
        return {
            "segment_id": response.get("id", name),
            "display_name": response.get("display_name", name),
            "state": response.get("state", "success"),
            "tier1_path": response.get("tier1_path", tier1_gateway),
            "subnets": self._subnet_gateways(response.get("subnets")) or subnets,
            "vlan": self._first_vlan(response.get("vlan_ids")) or vlan,
            "path": response.get("path", f"/infra/segments/{name}"),
            "tags": response.get("tags", tags or []),
        }

    async def get_segment(self, segment_id: str) -> dict[str, Any]:
        """Get segment details by ID."""
        logger.info(f"Getting NSX-T segment: {segment_id}")
        response = await self._request("GET", self._segment_path(segment_id))
        response["segment_id"] = response.get("id", segment_id)
        return response

    async def update_segment(
        self, segment_id: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """Update segment configuration."""
        logger.info(f"Updating NSX-T segment: {segment_id}")
        response = await self._request(
            "PATCH",
            self._segment_path(segment_id),
            json=updates,
        )
        return {
            "segment_id": response.get("id", segment_id),
            "state": response.get("state", "success"),
            "updates_applied": updates,
        }

    async def list_segments(self) -> list[dict[str, Any]]:
        """List all segments."""
        logger.info("Listing NSX-T segments")
        response = await self._request("GET", "/policy/api/v1/infra/segments")
        return response.get("results", [])

    async def create_tier1_gateway(
        self,
        name: str,
        tier0_gateway: str,
        route_advertisement: dict[str, Any] | None = None,
        failover_mode: str = "NON_PREEMPTIVE",
    ) -> dict[str, Any]:
        """Create a Tier-1 gateway."""
        payload = {
            "display_name": name,
            "tier0_path": tier0_gateway,
            "route_advertisement_types": route_advertisement or {},
            "failover_mode": failover_mode,
        }
        logger.info(f"Creating NSX-T T1 gateway: {name}")
        response = await self._request(
            "PUT",
            f"/policy/api/v1/infra/tier-1s/{name}",
            json=payload,
        )
        return {
            "tier1_id": response.get("id", name),
            "display_name": response.get("display_name", name),
            "state": response.get("state", "success"),
            "tier0_path": response.get("tier0_path", tier0_gateway),
            "failover_mode": response.get("failover_mode", failover_mode),
            "path": response.get("path", f"/infra/tier-1s/{name}"),
        }

    async def create_nat_rule(
        self,
        tier1_id: str,
        rule_id: str,
        action: str,
        translated_network: str,
        source_network: str | None = None,
        destination_network: str | None = None,
    ) -> dict[str, Any]:
        """Create a NAT rule on a Tier-1 gateway."""
        payload = {
            "action": action,
            "translated_network": translated_network,
        }
        if source_network is not None:
            payload["source_network"] = source_network
        if destination_network is not None:
            payload["destination_network"] = destination_network

        logger.info(f"Creating NAT rule {rule_id} on T1 {tier1_id}")
        response = await self._request(
            "PUT",
            f"/policy/api/v1/infra/tier-1s/{tier1_id}/nat/USER/nat-rules/{rule_id}",
            json=payload,
        )
        return {
            "rule_id": response.get("id", rule_id),
            "tier1_id": tier1_id,
            "action": response.get("action", action),
            "translated_network": response.get(
                "translated_network",
                translated_network,
            ),
            "source_network": response.get("source_network", source_network),
            "state": response.get("state", "success"),
        }

    async def create_firewall_rule(
        self,
        tier1_id: str,
        rule_id: str,
        display_name: str,
        action: str,
        services: list[str],
        source_groups: list[str] | None = None,
        destination_groups: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a gateway firewall rule for a Tier-1 gateway."""
        payload = {
            "display_name": display_name,
            "action": action,
            "services": services,
            "source_groups": source_groups or [],
            "destination_groups": destination_groups or [],
        }
        logger.info(f"Creating firewall rule {rule_id} on T1 {tier1_id}")
        response = await self._request(
            "PUT",
            (
                "/policy/api/v1/infra/domains/default/gateway-policies/"
                f"{tier1_id}/rules/{rule_id}"
            ),
            json=payload,
        )
        return {
            "rule_id": response.get("id", rule_id),
            "tier1_id": tier1_id,
            "display_name": response.get("display_name", display_name),
            "action": response.get("action", action),
            "services": response.get("services", services),
            "state": response.get("state", "success"),
        }
