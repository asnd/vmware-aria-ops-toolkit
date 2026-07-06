"""Standard API response models."""

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DetailedHealthResponse(HealthResponse):
    """Detailed health check response."""

    sites_reachable: int = 0
    sites_unreachable: int = 0
    jobs_running: int = 0
    jobs_pending: int = 0
    uptime_seconds: int = 0


class SuccessResponse(BaseModel):
    """Generic success response."""

    success: bool = True
    message: str
    data: dict[str, Any] | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated list response."""

    items: list[T]
    total: int
    page: int = Field(ge=1, default=1)
    page_size: int = Field(ge=1, le=1000, default=100)
    has_next: bool = False
    has_prev: bool = False

    @classmethod
    def create(
        cls, items: list[T], total: int, page: int = 1, page_size: int = 100
    ) -> "PaginatedResponse[T]":
        """Create paginated response with calculated fields."""
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_next=(page * page_size) < total,
            has_prev=page > 1,
        )
