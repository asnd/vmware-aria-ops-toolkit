"""Base operation handler for async operations."""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from app.core.audit_log import AuditLogger
from app.core.job_tracker import JobTracker
from app.models.job import JobStatus

logger = logging.getLogger(__name__)


class BaseOperation(ABC):
    """Base class for all async operations."""

    def __init__(self, job_tracker: JobTracker, audit_logger: AuditLogger):
        self.job_tracker = job_tracker
        self.audit_logger = audit_logger

    @abstractmethod
    async def execute(self, **kwargs) -> dict[str, Any]:
        """
        Execute the operation.

        Args:
            **kwargs: Operation-specific parameters

        Returns:
            Dictionary with operation result

        Raises:
            Exception: If operation fails
        """
        pass

    async def run_async(
        self,
        job_id: str,
        site_id: str,
        user: str,
        user_role: str,
        operation_name: str,
        **kwargs,
    ) -> None:
        """
        Run operation asynchronously with job tracking and audit logging.

        Args:
            job_id: Job ID for tracking
            site_id: Site ID where operation is performed
            user: Username who initiated operation
            user_role: User's role
            operation_name: Operation name for logging
            **kwargs: Operation-specific parameters
        """
        start_time = datetime.now(UTC)

        try:
            # Update job status to running
            await self.job_tracker.update_status(
                job_id, JobStatus.RUNNING, progress=10
            )

            # Log operation start
            await self.audit_logger.log_operation_started(
                job_id=job_id,
                operation=operation_name,
                site_id=site_id,
                user=user,
                user_role=user_role,
                request_body=kwargs,
            )

            # Execute the operation
            logger.info(f"Executing operation {operation_name} (job: {job_id})")
            result = await self.execute(**kwargs)

            # Calculate duration
            duration_ms = (
                datetime.now(UTC) - start_time
            ).total_seconds() * 1000

            # Mark job as completed
            await self.job_tracker.complete_job(job_id, result)

            # Log success
            await self.audit_logger.log_operation_completed(
                job_id=job_id,
                operation=operation_name,
                site_id=site_id,
                user=user,
                result=result,
                duration_ms=duration_ms,
            )

            logger.info(
                f"Operation {operation_name} completed successfully (job: {job_id}, duration: {duration_ms:.2f}ms)"
            )

        except Exception as e:
            # Calculate duration
            duration_ms = (
                datetime.now(UTC) - start_time
            ).total_seconds() * 1000

            error_msg = str(e)

            # Mark job as failed
            await self.job_tracker.fail_job(job_id, error_msg)

            # Log failure
            await self.audit_logger.log_operation_failed(
                job_id=job_id,
                operation=operation_name,
                site_id=site_id,
                user=user,
                error=error_msg,
                duration_ms=duration_ms,
            )

            logger.error(
                f"Operation {operation_name} failed (job: {job_id}): {error_msg}"
            )
