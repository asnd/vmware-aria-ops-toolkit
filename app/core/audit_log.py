"""Structured audit logging for compliance and state reconstruction."""

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import aiofiles

from app.config import settings

logger = logging.getLogger(__name__)


class AuditEventType(str, Enum):
    """Audit event types."""

    REQUEST = "request"
    RESPONSE = "response"
    OPERATION_STARTED = "operation.started"
    OPERATION_COMPLETED = "operation.completed"
    OPERATION_FAILED = "operation.failed"
    OPERATION_BLOCKED = "operation.blocked"
    AUTHENTICATION = "authentication"
    AUTHORIZATION_DENIED = "authorization.denied"
    CONFIG_RELOAD = "config.reload"


@dataclass
class AuditEvent:
    """Audit event model."""

    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_type: AuditEventType = AuditEventType.REQUEST
    request_id: str | None = None
    user: str | None = None
    user_role: str | None = None
    operation: str | None = None
    site_id: str | None = None
    job_id: str | None = None
    idempotency_key: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    http_method: str | None = None
    http_path: str | None = None
    http_status: int | None = None
    duration_ms: float | None = None
    request_body: dict[str, Any] | None = None
    response_body: dict[str, Any] | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        """Convert event to JSON string."""
        data = asdict(self)

        # Convert datetime to ISO format
        if isinstance(data["timestamp"], datetime):
            data["timestamp"] = data["timestamp"].isoformat()

        # Convert enum to string
        if isinstance(data["event_type"], AuditEventType):
            data["event_type"] = data["event_type"].value

        return json.dumps(data, default=str)


class AuditLogger:
    """Structured audit logging to JSONL file."""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path or settings.audit_log_path
        self._ensure_log_directory()

    def _ensure_log_directory(self) -> None:
        """Ensure log directory exists."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    async def log_event(self, event: AuditEvent) -> None:
        """
        Write audit event to log file (JSONL format).

        Args:
            event: AuditEvent object
        """
        try:
            async with aiofiles.open(self.log_path, mode="a") as f:
                await f.write(event.to_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

    async def log_request(
        self,
        request_id: str,
        method: str,
        path: str,
        client_ip: str | None = None,
        user_agent: str | None = None,
        user: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        """Log HTTP request."""
        event = AuditEvent(
            event_type=AuditEventType.REQUEST,
            request_id=request_id,
            user=user,
            http_method=method,
            http_path=path,
            client_ip=client_ip,
            user_agent=user_agent,
            request_body=body,
        )
        await self.log_event(event)

    async def log_response(
        self,
        request_id: str,
        status_code: int,
        duration_ms: float,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        """Log HTTP response."""
        event = AuditEvent(
            event_type=AuditEventType.RESPONSE,
            request_id=request_id,
            http_status=status_code,
            duration_ms=duration_ms,
            response_body=response_body,
        )
        await self.log_event(event)

    async def log_operation_started(
        self,
        job_id: str,
        operation: str,
        site_id: str,
        user: str,
        user_role: str,
        request_body: dict[str, Any] | None = None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        """Log operation start."""
        event = AuditEvent(
            event_type=AuditEventType.OPERATION_STARTED,
            request_id=request_id,
            user=user,
            user_role=user_role,
            operation=operation,
            site_id=site_id,
            job_id=job_id,
            idempotency_key=idempotency_key,
            request_body=request_body,
        )
        await self.log_event(event)

    async def log_operation_completed(
        self,
        job_id: str,
        operation: str,
        site_id: str,
        user: str,
        result: dict[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Log operation completion."""
        event = AuditEvent(
            event_type=AuditEventType.OPERATION_COMPLETED,
            user=user,
            operation=operation,
            site_id=site_id,
            job_id=job_id,
            response_body=result,
            duration_ms=duration_ms,
        )
        await self.log_event(event)

    async def log_operation_failed(
        self,
        job_id: str,
        operation: str,
        site_id: str,
        user: str,
        error: str,
        duration_ms: float | None = None,
    ) -> None:
        """Log operation failure."""
        event = AuditEvent(
            event_type=AuditEventType.OPERATION_FAILED,
            user=user,
            operation=operation,
            site_id=site_id,
            job_id=job_id,
            error=error,
            duration_ms=duration_ms,
        )
        await self.log_event(event)

    async def log_blocked_operation(
        self,
        user: str,
        user_role: str,
        operation: str,
        site_id: str | None,
        reason: str,
        request_id: str | None = None,
    ) -> None:
        """Log blocked operation attempt."""
        event = AuditEvent(
            event_type=AuditEventType.OPERATION_BLOCKED,
            request_id=request_id,
            user=user,
            user_role=user_role,
            operation=operation,
            site_id=site_id,
            error=reason,
        )
        await self.log_event(event)

    async def log_authentication(
        self,
        username: str,
        success: bool,
        client_ip: str | None = None,
        error: str | None = None,
    ) -> None:
        """Log authentication attempt."""
        event = AuditEvent(
            event_type=AuditEventType.AUTHENTICATION,
            user=username,
            client_ip=client_ip,
            metadata={"success": success},
            error=error,
        )
        await self.log_event(event)

    async def log_authorization_denied(
        self,
        user: str,
        user_role: str,
        required_permission: str,
        request_id: str | None = None,
        path: str | None = None,
    ) -> None:
        """Log authorization denial."""
        event = AuditEvent(
            event_type=AuditEventType.AUTHORIZATION_DENIED,
            request_id=request_id,
            user=user,
            user_role=user_role,
            http_path=path,
            metadata={"required_permission": required_permission},
        )
        await self.log_event(event)

    async def log_config_reload(
        self,
        user: str,
        config_type: str,
        success: bool,
        error: str | None = None,
    ) -> None:
        """Log configuration reload."""
        event = AuditEvent(
            event_type=AuditEventType.CONFIG_RELOAD,
            user=user,
            metadata={"config_type": config_type, "success": success},
            error=error,
        )
        await self.log_event(event)


# Global audit logger instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
