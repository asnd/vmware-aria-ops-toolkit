"""NSX-T operation request/response models."""

from pydantic import BaseModel, Field

# ==================== Segment Models ====================


class SegmentCreateRequest(BaseModel):
    """Request to create NSX-T segment."""

    name: str = Field(..., min_length=1, max_length=255, description="Segment name")
    tier1_gateway: str = Field(..., description="T1 gateway path")
    subnets: list[str] = Field(..., min_items=1, description="List of subnet CIDRs")
    vlan: int | None = Field(None, ge=1, le=4094, description="VLAN ID")
    tags: list[dict[str, str]] = Field(
        default_factory=list, description="Optional tags"
    )


class SegmentUpdateRequest(BaseModel):
    """Request to update NSX-T segment."""

    description: str | None = Field(None, description="Updated description")
    tags: list[dict[str, str]] | None = Field(None, description="Updated tags")


class SegmentResponse(BaseModel):
    """NSX-T segment response."""

    segment_id: str
    display_name: str
    state: str
    path: str
    site_id: str


# ==================== Tier-1 Gateway Models ====================


class Tier1GatewayCreateRequest(BaseModel):
    """Request to create T1 gateway."""

    name: str = Field(..., min_length=1, description="T1 gateway name")
    tier0_gateway: str = Field(..., description="T0 gateway path")
    route_advertisement: dict[str, bool] | None = Field(
        None, description="Route advertisement configuration"
    )
    failover_mode: str = Field(
        default="NON_PREEMPTIVE", description="Failover mode"
    )


class Tier1GatewayResponse(BaseModel):
    """T1 gateway response."""

    tier1_id: str
    display_name: str
    state: str
    tier0_path: str
    path: str


# ==================== NAT Rule Models ====================


class NATRuleCreateRequest(BaseModel):
    """Request to create NAT rule."""

    rule_id: str = Field(..., description="NAT rule ID")
    action: str = Field(
        ..., description="NAT action (SNAT, DNAT, NO_SNAT, NO_DNAT, REFLEXIVE)"
    )
    translated_network: str = Field(..., description="Translated network/IP")
    source_network: str | None = Field(None, description="Source network/IP")
    destination_network: str | None = Field(None, description="Destination network/IP")
    enabled: bool = Field(default=True, description="Enable rule")


class NATRuleResponse(BaseModel):
    """NAT rule response."""

    rule_id: str
    tier1_id: str
    action: str
    translated_network: str
    state: str


# ==================== Firewall Rule Models ====================


class FirewallRuleCreateRequest(BaseModel):
    """Request to create firewall rule."""

    rule_id: str = Field(..., description="Firewall rule ID")
    display_name: str = Field(..., description="Display name")
    action: str = Field(..., description="Action (ALLOW, DROP, REJECT)")
    services: list[str] = Field(..., description="List of services")
    source_groups: list[str] | None = Field(None, description="Source groups")
    destination_groups: list[str] | None = Field(None, description="Destination groups")
    enabled: bool = Field(default=True, description="Enable rule")


class FirewallRuleResponse(BaseModel):
    """Firewall rule response."""

    rule_id: str
    tier1_id: str
    display_name: str
    action: str
    state: str
