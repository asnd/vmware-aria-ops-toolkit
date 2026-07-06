"""AVI Controller API client backed by raw httpx requests."""

import logging
from typing import Any

import httpx

from app.clients.base_client import BaseClient
from app.core.inventory import AVIEndpoint

logger = logging.getLogger(__name__)


class AVIClient(BaseClient):
    """AVI Controller REST client."""

    def __init__(self, endpoint: AVIEndpoint):
        super().__init__("AVI")
        self.endpoint = endpoint
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        """Initialize the HTTP client used for AVI API requests."""
        if self._client is not None:
            return

        logger.info(f"Connecting to AVI Controller: {self.endpoint.controller_url}")
        self._client = httpx.AsyncClient(
            base_url=f"{self.endpoint.controller_url.rstrip('/')}/api/",
            auth=httpx.BasicAuth(self.endpoint.username, self.endpoint.password),
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Avi-Tenant": self.endpoint.tenant,
                "X-Avi-Version": self.endpoint.api_version,
            },
            timeout=httpx.Timeout(
                self.operation_timeout,
                connect=self.connection_timeout,
            ),
            verify=self.endpoint.verify_ssl,
        )

    async def disconnect(self) -> None:
        """Close the underlying HTTP client."""
        logger.info("Disconnecting from AVI Controller")
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
        """Execute an AVI API request and return the decoded JSON payload."""
        await self.connect()
        client = self._client
        if client is None:
            raise RuntimeError("AVI client is not connected")

        async def _send() -> dict[str, Any]:
            response = await client.request(method, path, json=json)
            response.raise_for_status()
            if not response.content:
                return {}
            return response.json()

        return await self.execute_with_retry(_send)

    async def create_virtual_service(
        self,
        name: str,
        vip: str,
        pool_ref: str,
        services: list[dict[str, Any]],
        application_profile_ref: str | None = None,
    ) -> dict[str, Any]:
        """Create an AVI virtual service."""
        payload: dict[str, Any] = {
            "name": name,
            "vip": [{"ip_address": {"addr": vip, "type": "V4"}}],
            "pool_ref": pool_ref,
            "services": services,
        }
        if application_profile_ref is not None:
            payload["application_profile_ref"] = application_profile_ref

        logger.info(f"Creating AVI Virtual Service: {name}")
        response = await self._request("POST", "virtualservice", json=payload)
        return {
            "uuid": response.get("uuid", f"vs-{name}"),
            "name": response.get("name", name),
            "vip": vip,
            "pool_ref": response.get("pool_ref", pool_ref),
            "services": response.get("services", services),
            "state": response.get("runtime", {})
            .get("oper_status", {})
            .get(
                "state",
                "OPER_UP",
            ),
            "url": response.get(
                "url", f"/api/virtualservice/{response.get('uuid', name)}"
            ),
        }

    async def get_virtual_service(self, vs_uuid: str) -> dict[str, Any]:
        """Get virtual service details."""
        logger.info(f"Getting AVI Virtual Service: {vs_uuid}")
        return await self._request("GET", f"virtualservice/{vs_uuid}")

    async def update_virtual_service(
        self, vs_uuid: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """Update virtual service configuration."""
        logger.info(f"Updating AVI Virtual Service: {vs_uuid}")
        response = await self._request("PUT", f"virtualservice/{vs_uuid}", json=updates)
        return {
            "uuid": response.get("uuid", vs_uuid),
            "state": response.get("state", "success"),
            "updates_applied": updates,
        }

    async def list_virtual_services(self) -> list[dict[str, Any]]:
        """List all virtual services."""
        logger.info("Listing AVI Virtual Services")
        response = await self._request("GET", "virtualservice")
        return response.get("results", [])

    async def create_pool(
        self,
        name: str,
        servers: list[dict[str, Any]],
        health_monitor_refs: list[str] | None = None,
        lb_algorithm: str = "LB_ALGORITHM_LEAST_CONNECTIONS",
    ) -> dict[str, Any]:
        """Create an AVI pool."""
        payload = {
            "name": name,
            "servers": [
                {"ip": {"addr": server["ip"], "type": "V4"}, "port": server["port"]}
                for server in servers
            ],
            "health_monitor_refs": health_monitor_refs or [],
            "lb_algorithm": lb_algorithm,
        }
        logger.info(f"Creating AVI Pool: {name}")
        response = await self._request("POST", "pool", json=payload)
        return {
            "uuid": response.get("uuid", f"pool-{name}"),
            "name": response.get("name", name),
            "servers": servers,
            "health_monitor_refs": response.get(
                "health_monitor_refs",
                health_monitor_refs or [],
            ),
            "lb_algorithm": response.get("lb_algorithm", lb_algorithm),
            "state": response.get("state", "success"),
        }

    async def get_pool(self, pool_uuid: str) -> dict[str, Any]:
        """Get pool details."""
        logger.info(f"Getting AVI Pool: {pool_uuid}")
        return await self._request("GET", f"pool/{pool_uuid}")

    async def update_pool(
        self, pool_uuid: str, updates: dict[str, Any]
    ) -> dict[str, Any]:
        """Update pool configuration."""
        logger.info(f"Updating AVI Pool: {pool_uuid}")
        response = await self._request("PUT", f"pool/{pool_uuid}", json=updates)
        return {
            "uuid": response.get("uuid", pool_uuid),
            "state": response.get("state", "success"),
            "updates_applied": updates,
        }

    async def delete_pool(self, pool_uuid: str) -> dict[str, Any]:
        """Delete an AVI pool."""
        logger.info(f"Deleting AVI Pool: {pool_uuid}")
        response = await self._request("DELETE", f"pool/{pool_uuid}")
        return {
            "uuid": response.get("uuid", pool_uuid),
            "state": response.get("state", "deleted"),
        }

    async def assign_vip(
        self, ip_address: str, subnet: str, vip_name: str | None = None
    ) -> dict[str, Any]:
        """Assign or allocate a VIP."""
        payload = {
            "name": vip_name or f"vip-{ip_address}",
            "vip": [{"ip_address": {"addr": ip_address, "type": "V4"}}],
            "subnet": subnet,
        }
        logger.info(f"Assigning AVI VIP: {ip_address}")
        response = await self._request("POST", "vsvip", json=payload)
        return {
            "vip_id": response.get("uuid", f"vip-{ip_address.replace('.', '-')}"),
            "ip_address": ip_address,
            "subnet": subnet,
            "name": response.get("name", payload["name"]),
            "state": response.get("state", "allocated"),
        }
