"""NSX-T segment operations."""

import logging
from typing import Any

from app.clients.nsxt_client import NSXTClient
from app.core.inventory import get_inventory
from app.operations.base import BaseOperation

logger = logging.getLogger(__name__)


class SegmentCreateOperation(BaseOperation):
    """Create NSX-T segment operation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """
        Execute segment creation.

        Expected kwargs:
            - site_id: Site ID
            - name: Segment name
            - tier1_gateway: T1 gateway path
            - subnets: List of subnet CIDRs
            - vlan: Optional VLAN ID
            - tags: Optional tags
        """
        site_id = kwargs["site_id"]
        name = kwargs["name"]
        tier1_gateway = kwargs["tier1_gateway"]
        subnets = kwargs["subnets"]
        vlan = kwargs.get("vlan")
        tags = kwargs.get("tags", [])

        # Get site from inventory
        inventory = get_inventory()
        site = inventory.get_site(site_id)

        if not site:
            raise ValueError(f"Site not found: {site_id}")

        if not site.has_nsxt():
            raise ValueError(f"Site {site_id} does not have NSX-T configured")

        # Create NSX-T client
        client = NSXTClient(site.nsxt)

        # Connect to NSX-T Manager
        await client.connect()

        try:
            # Update progress
            await self.job_tracker.update_status(
                kwargs.get("_job_id", "unknown"), progress=30
            )

            # Create segment
            result = await client.create_segment(
                name=name,
                tier1_gateway=tier1_gateway,
                subnets=subnets,
                vlan=vlan,
                tags=tags,
            )

            # Update progress
            await self.job_tracker.update_status(
                kwargs.get("_job_id", "unknown"), progress=90
            )

            return {
                "segment_id": result["segment_id"],
                "display_name": result["display_name"],
                "state": result["state"],
                "path": result["path"],
                "site_id": site_id,
                "subnets": result["subnets"],
                "vlan": result.get("vlan"),
            }

        finally:
            await client.disconnect()


class SegmentUpdateOperation(BaseOperation):
    """Update NSX-T segment operation."""

    async def execute(self, **kwargs) -> dict[str, Any]:
        """
        Execute segment update.

        Expected kwargs:
            - site_id: Site ID
            - segment_id: Segment ID to update
            - updates: Dictionary of updates to apply
        """
        site_id = kwargs["site_id"]
        segment_id = kwargs["segment_id"]
        updates = kwargs["updates"]

        # Get site from inventory
        inventory = get_inventory()
        site = inventory.get_site(site_id)

        if not site or not site.has_nsxt():
            raise ValueError(f"Site {site_id} not found or NSX-T not configured")

        # Create NSX-T client
        client = NSXTClient(site.nsxt)
        await client.connect()

        try:
            await self.job_tracker.update_status(
                kwargs.get("_job_id", "unknown"), progress=30
            )

            result = await client.update_segment(segment_id, updates)

            await self.job_tracker.update_status(
                kwargs.get("_job_id", "unknown"), progress=90
            )

            return {
                "segment_id": segment_id,
                "state": result["state"],
                "updates_applied": updates,
                "site_id": site_id,
            }

        finally:
            await client.disconnect()
