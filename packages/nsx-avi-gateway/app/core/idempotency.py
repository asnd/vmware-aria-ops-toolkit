"""Idempotency key management for preventing duplicate operations."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class IdempotentRequest:
    """Cached idempotent request."""

    key: str
    job_id: str
    response: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
        + timedelta(seconds=settings.idempotency_cache_ttl_seconds)
    )


class IdempotencyManager:
    """Manage idempotent request caching."""

    def __init__(self):
        self._cache: dict[str, IdempotentRequest] = {}
        self._lock = asyncio.Lock()

    async def check_key(self, key: str) -> IdempotentRequest | None:
        """
        Check if an idempotency key exists in cache.

        Args:
            key: Idempotency key

        Returns:
            IdempotentRequest if found and not expired, None otherwise
        """
        async with self._lock:
            request = self._cache.get(key)
            if not request:
                return None

            # Check if expired
            if datetime.now(UTC) > request.expires_at:
                del self._cache[key]
                logger.debug(f"Idempotency key expired: {key}")
                return None

            logger.info(f"Idempotency key found (cache hit): {key}")
            return request

    async def store_result(
        self,
        key: str,
        job_id: str,
        response: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        """
        Store a response for an idempotency key.

        Args:
            key: Idempotency key
            job_id: Associated job ID
            response: Response dictionary to cache
            ttl_seconds: Optional custom TTL (uses config default if not provided)
        """
        ttl = ttl_seconds or settings.idempotency_cache_ttl_seconds

        async with self._lock:
            request = IdempotentRequest(
                key=key,
                job_id=job_id,
                response=response,
                created_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
            )

            self._cache[key] = request
            logger.info(f"Stored idempotency key: {key} (job: {job_id}, ttl: {ttl}s)")

    async def invalidate_key(self, key: str) -> bool:
        """
        Invalidate (remove) an idempotency key from cache.

        Args:
            key: Idempotency key

        Returns:
            True if key was removed, False if not found
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.info(f"Invalidated idempotency key: {key}")
                return True
            return False

    async def cleanup_expired(self) -> int:
        """
        Remove all expired idempotency keys from cache.

        Returns:
            Number of keys removed
        """
        now = datetime.now(UTC)

        async with self._lock:
            expired_keys = [
                key for key, request in self._cache.items() if now > request.expires_at
            ]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired idempotency keys")

            return len(expired_keys)

    async def get_stats(self) -> dict[str, Any]:
        """
        Get idempotency cache statistics.

        Returns:
            Dictionary with statistics
        """
        async with self._lock:
            stats = {
                "cached_keys": len(self._cache),
                "oldest_key_age_seconds": None,
            }

            if self._cache:
                oldest = min(self._cache.values(), key=lambda r: r.created_at)
                age = (datetime.now(UTC) - oldest.created_at).total_seconds()
                stats["oldest_key_age_seconds"] = int(age)

            return stats


# Global idempotency manager instance
_idempotency_manager: IdempotencyManager | None = None


def get_idempotency_manager() -> IdempotencyManager:
    """Get the global idempotency manager instance."""
    global _idempotency_manager
    if _idempotency_manager is None:
        _idempotency_manager = IdempotencyManager()
    return _idempotency_manager
