"""NSX-T operation API endpoints."""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

from app.auth.rbac import RBACChecker
from app.core.allowlist import get_allowlist
from app.core.audit_log import get_audit_logger
from app.core.job_tracker import get_job_tracker
from app.models.auth import User
from app.models.job import JobResponse
from app.models.nsxt import SegmentCreateRequest, SegmentUpdateRequest
from app.operations.nsxt.segments import SegmentCreateOperation, SegmentUpdateOperation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/nsxt", tags=["nsxt"])


@router.post("/{site_id}/segments", response_model=JobResponse)
async def create_segment(
    site_id: str,
    request_data: SegmentCreateRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
    current_user: User = Depends(RBACChecker("nsxt:segment:create")),
):
    """
    Create NSX-T segment (async operation).

    Returns job ID for tracking operation status.
    """
    operation_name = "nsxt.segment.create"

    # Validate operation against allowlist
    allowlist = get_allowlist()
    audit_logger = get_audit_logger()

    if not allowlist.is_allowed(operation_name, current_user.primary_role, site_id):
        reason = allowlist.get_blocked_reason(operation_name)

        # Log blocked operation
        await audit_logger.log_blocked_operation(
            user=current_user.username,
            user_role=current_user.primary_role,
            operation=operation_name,
            site_id=site_id,
            reason=reason,
            request_id=getattr(http_request.state, "request_id", None),
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operation blocked: {reason}",
        )

    # Create job
    job_tracker = get_job_tracker()
    idempotency_key = http_request.headers.get("idempotency-key")

    job_id = await job_tracker.create_job(
        operation=operation_name,
        site_id=site_id,
        user=current_user.username,
        idempotency_key=idempotency_key,
        metadata={"request": request_data.dict()},
    )

    # Run operation in background
    operation = SegmentCreateOperation(job_tracker, audit_logger)

    params = request_data.dict()
    params["site_id"] = site_id
    params["_job_id"] = job_id  # Pass job_id for progress updates

    background_tasks.add_task(
        operation.run_async,
        job_id=job_id,
        site_id=site_id,
        user=current_user.username,
        user_role=current_user.primary_role,
        operation_name=operation_name,
        **params,
    )

    logger.info(
        f"Created job {job_id} for {operation_name} on site {site_id} by {current_user.username}"
    )

    return JobResponse(
        job_id=job_id,
        operation=operation_name,
        site_id=site_id,
        status="pending",
        progress=0,
        created_at=job_tracker._jobs[job_id].created_at,
        user=current_user.username,
        idempotency_key=idempotency_key,
    )


@router.patch("/{site_id}/segments/{segment_id}", response_model=JobResponse)
async def update_segment(
    site_id: str,
    segment_id: str,
    request_data: SegmentUpdateRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
    current_user: User = Depends(RBACChecker("nsxt:segment:update")),
):
    """
    Update NSX-T segment (async operation).

    Returns job ID for tracking operation status.
    """
    operation_name = "nsxt.segment.update"

    # Validate operation against allowlist
    allowlist = get_allowlist()
    audit_logger = get_audit_logger()

    if not allowlist.is_allowed(operation_name, current_user.primary_role, site_id):
        reason = allowlist.get_blocked_reason(operation_name)

        await audit_logger.log_blocked_operation(
            user=current_user.username,
            user_role=current_user.primary_role,
            operation=operation_name,
            site_id=site_id,
            reason=reason,
            request_id=getattr(http_request.state, "request_id", None),
        )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operation blocked: {reason}",
        )

    # Create job
    job_tracker = get_job_tracker()
    idempotency_key = http_request.headers.get("idempotency-key")

    job_id = await job_tracker.create_job(
        operation=operation_name,
        site_id=site_id,
        user=current_user.username,
        idempotency_key=idempotency_key,
        metadata={"segment_id": segment_id, "updates": request_data.dict()},
    )

    # Run operation in background
    operation = SegmentUpdateOperation(job_tracker, audit_logger)

    background_tasks.add_task(
        operation.run_async,
        job_id=job_id,
        site_id=site_id,
        user=current_user.username,
        user_role=current_user.primary_role,
        operation_name=operation_name,
        segment_id=segment_id,
        updates=request_data.dict(exclude_none=True),
        _job_id=job_id,
    )

    logger.info(
        f"Created job {job_id} for {operation_name} on segment {segment_id} (site {site_id}) by {current_user.username}"
    )

    return JobResponse(
        job_id=job_id,
        operation=operation_name,
        site_id=site_id,
        status="pending",
        progress=0,
        created_at=job_tracker._jobs[job_id].created_at,
        user=current_user.username,
        idempotency_key=idempotency_key,
    )


# TODO: Add more NSX-T endpoints:
# - GET /{site_id}/segments - List segments
# - GET /{site_id}/segments/{segment_id} - Get segment details
# - POST /{site_id}/tier1-gateways - Create T1 gateway
# - POST /{site_id}/tier1-gateways/{t1_id}/nat-rules - Create NAT rule
# - POST /{site_id}/tier1-gateways/{t1_id}/firewall-rules - Create FW rule
