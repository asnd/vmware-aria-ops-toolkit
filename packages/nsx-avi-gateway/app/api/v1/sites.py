"""Site inventory API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.auth.oauth2 import get_current_active_user
from app.auth.rbac import require_role
from app.core.audit_log import get_audit_logger
from app.core.inventory import get_inventory, reload_inventory
from app.models.auth import User
from app.models.responses import SuccessResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sites", tags=["sites"])


class SiteResponse(BaseModel):
    """Site information response."""

    site_id: str
    name: str
    region: str
    has_nsxt: bool
    has_avi: bool
    tags: dict[str, str]


class SiteListResponse(BaseModel):
    """List of sites response."""

    sites: list[SiteResponse]
    total: int


@router.get("/", response_model=SiteListResponse)
async def list_sites(
    region: str | None = Query(None, description="Filter by region"),
    environment: str | None = Query(None, description="Filter by environment tag"),
    current_user: User = Depends(get_current_active_user),
):
    """
    List all sites with optional filtering.

    Query parameters:
    - region: Filter by region
    - environment: Filter by environment tag
    """
    inventory = get_inventory()

    # Build tag filters
    filters = {}
    if environment:
        filters["environment"] = environment

    sites = inventory.get_sites(filters=filters if filters else None)

    # Apply region filter if provided
    if region:
        sites = [s for s in sites if s.region == region]

    # Convert to response models
    site_responses = [
        SiteResponse(
            site_id=site.site_id,
            name=site.name,
            region=site.region,
            has_nsxt=site.has_nsxt(),
            has_avi=site.has_avi(),
            tags=site.tags,
        )
        for site in sites
    ]

    return SiteListResponse(
        sites=site_responses,
        total=len(site_responses),
    )


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """Get site details by ID."""
    inventory = get_inventory()
    site = inventory.get_site(site_id)

    if not site:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Site not found: {site_id}",
        )

    return SiteResponse(
        site_id=site.site_id,
        name=site.name,
        region=site.region,
        has_nsxt=site.has_nsxt(),
        has_avi=site.has_avi(),
        tags=site.tags,
    )


@router.post("/reload", response_model=SuccessResponse)
async def reload_site_inventory(
    current_user: User = Depends(require_role("admin")),
):
    """
    Reload site inventory from configuration file (admin only).

    This allows updating site configuration without restarting the application.
    """
    audit_logger = get_audit_logger()

    try:
        inventory = reload_inventory()
        site_count = inventory.get_site_count()

        # Log configuration reload
        await audit_logger.log_config_reload(
            user=current_user.username,
            config_type="sites",
            success=True,
        )

        logger.info(
            f"Site inventory reloaded by {current_user.username}: {site_count} sites"
        )

        return SuccessResponse(
            success=True,
            message=f"Site inventory reloaded successfully: {site_count} sites",
            data={"sites_loaded": site_count},
        )

    except Exception as e:
        # Log failure
        await audit_logger.log_config_reload(
            user=current_user.username,
            config_type="sites",
            success=False,
            error=str(e),
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reload site inventory: {str(e)}",
        )
