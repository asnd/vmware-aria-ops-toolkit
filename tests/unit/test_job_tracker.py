"""Unit tests for job tracker."""

import pytest

from app.core.job_tracker import JobTracker
from app.models.job import JobStatus


class TestJobTracker:
    """Test suite for JobTracker class."""

    @pytest.mark.asyncio
    async def test_create_job(self):
        """Test creating a new job."""
        tracker = JobTracker()

        job_id = await tracker.create_job(
            operation="test.operation",
            site_id="test-site",
            user="test-user",
        )

        assert job_id is not None
        assert job_id.startswith("job_")

        job = await tracker.get_job(job_id)
        assert job is not None
        assert job.operation == "test.operation"
        assert job.site_id == "test-site"
        assert job.user == "test-user"
        assert job.status == JobStatus.PENDING

    @pytest.mark.asyncio
    async def test_update_job_status(self):
        """Test updating job status."""
        tracker = JobTracker()

        job_id = await tracker.create_job(
            operation="test.operation",
            site_id="test-site",
            user="test-user",
        )

        # Update to running
        await tracker.update_status(job_id, JobStatus.RUNNING, progress=50)

        job = await tracker.get_job(job_id)
        assert job.status == JobStatus.RUNNING
        assert job.progress == 50

    @pytest.mark.asyncio
    async def test_complete_job(self):
        """Test completing a job."""
        tracker = JobTracker()

        job_id = await tracker.create_job(
            operation="test.operation",
            site_id="test-site",
            user="test-user",
        )

        result = {"success": True, "data": "test-data"}
        await tracker.complete_job(job_id, result)

        job = await tracker.get_job(job_id)
        assert job.status == JobStatus.COMPLETED
        assert job.progress == 100
        assert job.result == result
        assert job.completed_at is not None

    @pytest.mark.asyncio
    async def test_fail_job(self):
        """Test failing a job."""
        tracker = JobTracker()

        job_id = await tracker.create_job(
            operation="test.operation",
            site_id="test-site",
            user="test-user",
        )

        error_msg = "Test error message"
        await tracker.fail_job(job_id, error_msg)

        job = await tracker.get_job(job_id)
        assert job.status == JobStatus.FAILED
        assert job.error == error_msg
        assert job.completed_at is not None

    @pytest.mark.asyncio
    async def test_cancel_job(self):
        """Test cancelling a job."""
        tracker = JobTracker()

        job_id = await tracker.create_job(
            operation="test.operation",
            site_id="test-site",
            user="test-user",
        )

        cancelled = await tracker.cancel_job(job_id)
        assert cancelled is True

        job = await tracker.get_job(job_id)
        assert job.status == JobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_completed_job(self):
        """Test that completed jobs cannot be cancelled."""
        tracker = JobTracker()

        job_id = await tracker.create_job(
            operation="test.operation",
            site_id="test-site",
            user="test-user",
        )

        await tracker.complete_job(job_id, {"success": True})

        cancelled = await tracker.cancel_job(job_id)
        assert cancelled is False

    @pytest.mark.asyncio
    async def test_list_jobs_with_filters(self):
        """Test listing jobs with filters."""
        tracker = JobTracker()

        # Create multiple jobs
        job1_id = await tracker.create_job("op1", "site1", "user1")
        await tracker.create_job("op2", "site2", "user2")
        await tracker.create_job("op3", "site1", "user1")

        # Complete one job
        await tracker.complete_job(job1_id, {"result": "ok"})

        # Filter by site
        jobs, total = await tracker.list_jobs(filters={"site_id": "site1"})
        assert total == 2

        # Filter by status
        jobs, total = await tracker.list_jobs(filters={"status": JobStatus.COMPLETED})
        assert total == 1

        # Filter by user
        jobs, total = await tracker.list_jobs(filters={"user": "user1"})
        assert total == 2

    @pytest.mark.asyncio
    async def test_list_jobs_pagination(self):
        """Test job list pagination."""
        tracker = JobTracker()

        # Create 10 jobs
        for i in range(10):
            await tracker.create_job(f"op{i}", "site1", "user1")

        # Get first page
        jobs, total = await tracker.list_jobs(limit=5, offset=0)
        assert len(jobs) == 5
        assert total == 10

        # Get second page
        jobs, total = await tracker.list_jobs(limit=5, offset=5)
        assert len(jobs) == 5
        assert total == 10

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting job statistics."""
        tracker = JobTracker()

        # Create jobs in different states
        job1 = await tracker.create_job("op1", "site1", "user1")
        job2 = await tracker.create_job("op2", "site1", "user1")
        job3 = await tracker.create_job("op3", "site1", "user1")

        await tracker.update_status(job1, JobStatus.RUNNING)
        await tracker.complete_job(job2, {"ok": True})
        await tracker.fail_job(job3, "error")

        stats = await tracker.get_stats()

        assert stats["total_jobs_created"] == 3
        assert stats["running"] == 1
        assert stats["completed"] == 1
        assert stats["failed"] == 1

    @pytest.mark.asyncio
    async def test_idempotency_key(self):
        """Test job creation with idempotency key."""
        tracker = JobTracker()

        job_id = await tracker.create_job(
            operation="test.operation",
            site_id="test-site",
            user="test-user",
            idempotency_key="test-key-123",
        )

        job = await tracker.get_job(job_id)
        assert job.idempotency_key == "test-key-123"
