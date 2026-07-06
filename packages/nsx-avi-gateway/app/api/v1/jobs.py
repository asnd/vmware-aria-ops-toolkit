"""Job tracking API endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.oauth2 import get_current_active_user
from app.auth.rbac import require_role
from app.core.job_tracker import get_job_tracker
from app.models.auth import User
from app.models.job import JobDetail, JobList, JobResponse, JobStatus
from app.models.responses import SuccessResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobDetail)
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_active_user),
):
    """
    Get job status and result.

    Returns detailed job information including result or error.
    """
    job_tracker = get_job_tracker()
    job = await job_tracker.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    # Convert to response model
    job_dict = job.to_dict()

    return JobDetail(**job_dict)


@router.get("/", response_model=JobList)
async def list_jobs(
    status_filter: JobStatus | None = Query(None, alias="status"),
    site_id: str | None = Query(None),
    user_filter: str | None = Query(None, alias="user"),
    operation: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_active_user),
):
    """
    List jobs with optional filtering and pagination.

    Query parameters:
    - status: Filter by job status
    - site_id: Filter by site ID
    - user: Filter by username
    - operation: Filter by operation name
    - page: Page number (starts at 1)
    - page_size: Items per page (max 1000)
    """
    job_tracker = get_job_tracker()

    # Build filters
    filters = {}
    if status_filter:
        filters["status"] = status_filter
    if site_id:
        filters["site_id"] = site_id
    if user_filter:
        filters["user"] = user_filter
    if operation:
        filters["operation"] = operation

    # Get jobs with pagination
    offset = (page - 1) * page_size
    jobs, total = await job_tracker.list_jobs(
        filters=filters,
        limit=page_size,
        offset=offset,
    )

    # Convert to response models
    job_responses = [
        JobResponse(
            job_id=job.job_id,
            operation=job.operation,
            site_id=job.site_id,
            status=job.status,
            progress=job.progress,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
            user=job.user,
            idempotency_key=job.idempotency_key,
        )
        for job in jobs
    ]

    return JobList(
        jobs=job_responses,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/{job_id}/cancel", response_model=SuccessResponse)
async def cancel_job(
    job_id: str,
    current_user: User = Depends(require_role("admin")),
):
    """
    Cancel a running or pending job (admin only).

    Only jobs in PENDING or RUNNING status can be cancelled.
    """
    job_tracker = get_job_tracker()

    cancelled = await job_tracker.cancel_job(job_id)

    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Job cannot be cancelled (not found or already completed)",
        )

    logger.info(f"Job {job_id} cancelled by {current_user.username}")

    return SuccessResponse(
        success=True,
        message=f"Job {job_id} cancelled successfully",
    )


@router.get("/stats/summary")
async def get_job_stats(
    current_user: User = Depends(get_current_active_user),
):
    """Get job tracker statistics."""
    job_tracker = get_job_tracker()
    stats = await job_tracker.get_stats()

    return stats
