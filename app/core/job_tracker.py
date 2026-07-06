"""Async job tracking with in-memory storage."""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import settings
from app.models.job import JobStatus

logger = logging.getLogger(__name__)


@dataclass
class Job:
    """Internal job representation."""

    job_id: str
    operation: str
    site_id: str
    user: str
    status: JobStatus
    progress: int = 0  # 0-100
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    idempotency_key: str | None = None
    request_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert job to dictionary."""
        return {
            "job_id": self.job_id,
            "operation": self.operation,
            "site_id": self.site_id,
            "user": self.user,
            "status": self.status.value,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "idempotency_key": self.idempotency_key,
            "request_metadata": self.request_metadata,
        }


class JobTracker:
    """Thread-safe in-memory job tracking."""

    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()
        self._job_count = 0

    async def create_job(
        self,
        operation: str,
        site_id: str,
        user: str,
        idempotency_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Create a new job.

        Args:
            operation: Operation name (e.g., "nsxt.segment.create")
            site_id: Site ID where operation will be performed
            user: Username who initiated the operation
            idempotency_key: Optional idempotency key
            metadata: Optional metadata dict

        Returns:
            Job ID (UUID)

        Raises:
            RuntimeError: If max concurrent jobs limit reached
        """
        async with self._lock:
            # Check concurrent job limit
            active_jobs = sum(
                1
                for job in self._jobs.values()
                if job.status in (JobStatus.PENDING, JobStatus.RUNNING)
            )
            if active_jobs >= settings.max_concurrent_jobs:
                raise RuntimeError(
                    f"Maximum concurrent jobs limit reached: {settings.max_concurrent_jobs}"
                )

            job_id = f"job_{uuid.uuid4().hex[:12]}"

            job = Job(
                job_id=job_id,
                operation=operation,
                site_id=site_id,
                user=user,
                status=JobStatus.PENDING,
                idempotency_key=idempotency_key,
                request_metadata=metadata or {},
            )

            self._jobs[job_id] = job
            self._job_count += 1

            logger.info(
                f"Created job {job_id}: {operation} on site {site_id} by {user}"
            )

            return job_id

    async def update_status(
        self, job_id: str, status: JobStatus, progress: int = 0
    ) -> None:
        """
        Update job status and progress.

        Args:
            job_id: Job ID
            status: New status
            progress: Progress percentage (0-100)
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                logger.warning(f"Job not found: {job_id}")
                return

            job.status = status
            job.progress = max(0, min(100, progress))
            job.updated_at = datetime.now(UTC)

            if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                job.completed_at = datetime.now(UTC)

            logger.debug(f"Job {job_id} status updated: {status.value} ({progress}%)")

    async def complete_job(self, job_id: str, result: dict[str, Any]) -> None:
        """
        Mark job as completed with result.

        Args:
            job_id: Job ID
            result: Operation result dictionary
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                logger.warning(f"Job not found: {job_id}")
                return

            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.result = result
            job.updated_at = datetime.now(UTC)
            job.completed_at = datetime.now(UTC)

            logger.info(f"Job {job_id} completed successfully")

    async def fail_job(self, job_id: str, error: str) -> None:
        """
        Mark job as failed with error message.

        Args:
            job_id: Job ID
            error: Error message
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                logger.warning(f"Job not found: {job_id}")
                return

            job.status = JobStatus.FAILED
            job.error = error
            job.updated_at = datetime.now(UTC)
            job.completed_at = datetime.now(UTC)

            logger.error(f"Job {job_id} failed: {error}")

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a running or pending job.

        Args:
            job_id: Job ID

        Returns:
            True if cancelled, False if job not found or already completed
        """
        async with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False

            if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                return False  # Can't cancel already finished jobs

            job.status = JobStatus.CANCELLED
            job.updated_at = datetime.now(UTC)
            job.completed_at = datetime.now(UTC)

            logger.info(f"Job {job_id} cancelled")
            return True

    async def get_job(self, job_id: str) -> Job | None:
        """
        Get job by ID.

        Args:
            job_id: Job ID

        Returns:
            Job object or None if not found
        """
        async with self._lock:
            return self._jobs.get(job_id)

    async def list_jobs(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[Job], int]:
        """
        List jobs with optional filtering.

        Args:
            filters: Optional filters dict (status, site_id, user, operation)
            limit: Maximum number of jobs to return
            offset: Number of jobs to skip

        Returns:
            Tuple of (jobs list, total count)
        """
        async with self._lock:
            jobs = list(self._jobs.values())

            # Apply filters
            if filters:
                if "status" in filters:
                    status_filter = filters["status"]
                    if isinstance(status_filter, str):
                        status_filter = JobStatus(status_filter)
                    jobs = [j for j in jobs if j.status == status_filter]

                if "site_id" in filters:
                    jobs = [j for j in jobs if j.site_id == filters["site_id"]]

                if "user" in filters:
                    jobs = [j for j in jobs if j.user == filters["user"]]

                if "operation" in filters:
                    jobs = [j for j in jobs if j.operation == filters["operation"]]

            # Sort by creation time (newest first)
            jobs.sort(key=lambda j: j.created_at, reverse=True)

            total = len(jobs)

            # Apply pagination
            jobs = jobs[offset : offset + limit]

            return jobs, total

    async def cleanup_expired(self, retention_minutes: int | None = None) -> int:
        """
        Remove expired jobs from storage.

        Args:
            retention_minutes: Job retention time in minutes (uses config default if not provided)

        Returns:
            Number of jobs removed
        """
        retention = retention_minutes or settings.job_retention_minutes
        cutoff_time = datetime.now(UTC) - timedelta(minutes=retention)

        async with self._lock:
            expired_jobs = [
                job_id
                for job_id, job in self._jobs.items()
                if job.completed_at
                and job.completed_at < cutoff_time
                and job.status
                in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
            ]

            for job_id in expired_jobs:
                del self._jobs[job_id]

            if expired_jobs:
                logger.info(f"Cleaned up {len(expired_jobs)} expired jobs")

            return len(expired_jobs)

    async def get_stats(self) -> dict[str, Any]:
        """
        Get job tracker statistics.

        Returns:
            Dictionary with statistics
        """
        async with self._lock:
            stats = {
                "total_jobs_created": self._job_count,
                "active_jobs": len(self._jobs),
                "pending": sum(1 for j in self._jobs.values() if j.status == JobStatus.PENDING),
                "running": sum(1 for j in self._jobs.values() if j.status == JobStatus.RUNNING),
                "completed": sum(
                    1 for j in self._jobs.values() if j.status == JobStatus.COMPLETED
                ),
                "failed": sum(1 for j in self._jobs.values() if j.status == JobStatus.FAILED),
                "cancelled": sum(
                    1 for j in self._jobs.values() if j.status == JobStatus.CANCELLED
                ),
            }
            return stats


# Global job tracker instance
_job_tracker: JobTracker | None = None


def get_job_tracker() -> JobTracker:
    """Get the global job tracker instance."""
    global _job_tracker
    if _job_tracker is None:
        _job_tracker = JobTracker()
    return _job_tracker
