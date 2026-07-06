"""Base client with retry and timeout logic."""

import asyncio
import logging
from typing import Any, Callable

from app.config import settings

logger = logging.getLogger(__name__)


class BaseClient:
    """Base client with common retry/timeout functionality."""

    def __init__(self, name: str):
        self.name = name
        self.connection_timeout = settings.api_connection_timeout
        self.operation_timeout = settings.api_operation_timeout
        self.max_retries = settings.api_max_retries

    async def execute_with_retry(
        self,
        operation: Callable,
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute an operation with retry logic.

        Args:
            operation: Async function to execute
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation

        Returns:
            Operation result

        Raises:
            Exception: If all retries fail
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                result = await asyncio.wait_for(
                    operation(*args, **kwargs),
                    timeout=self.operation_timeout,
                )
                return result

            except asyncio.TimeoutError as e:
                last_exception = e
                logger.warning(
                    f"{self.name}: Operation timeout on attempt {attempt + 1}/{self.max_retries}"
                )

            except Exception as e:
                last_exception = e
                logger.warning(
                    f"{self.name}: Operation failed on attempt {attempt + 1}/{self.max_retries}: {e}"
                )

            # Exponential backoff
            if attempt < self.max_retries - 1:
                wait_time = 2**attempt
                logger.debug(f"{self.name}: Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)

        # All retries failed
        logger.error(f"{self.name}: All {self.max_retries} retries failed")
        raise last_exception or Exception(f"{self.name}: Operation failed after all retries")
