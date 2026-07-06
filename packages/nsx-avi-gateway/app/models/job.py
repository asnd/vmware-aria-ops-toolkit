"""Job tracking models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Job status enumeration."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCreate(BaseModel):
    """Job creation request."""

    operation: str
    site_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class JobResponse(BaseModel):
    """Job response model."""

    job_id: str
    operation: str
    site_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100, default=0)
    created_at: datetime
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    user: str | None = None
    idempotency_key: str | None = None


class JobDetail(JobResponse):
    """Detailed job information including result/error."""

    result: dict[str, Any] | None = None
    error: str | None = None
    request_metadata: dict[str, Any] = Field(default_factory=dict)


class JobList(BaseModel):
    """Paginated job list response."""

    jobs: list[JobResponse]
    total: int
    page: int = 1
    page_size: int = 100
