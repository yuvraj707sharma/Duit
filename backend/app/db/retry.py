"""Retryable Transient Error and Optimistic Locking Support for DUIT Database Layer.

Provides automated exponential backoff with jitter on transient database connection/lock errors
and optimistic locking concurrency control.
"""
import asyncio
import logging
import random
from typing import Callable, TypeVar, Any, Optional
from sqlalchemy.exc import DBAPIError, OperationalError, InterfaceError

logger = logging.getLogger(__name__)

T = TypeVar("T")


class OptimisticLockError(Exception):
    """Raised when an entity update fails due to a concurrent version mismatch."""
    pass


TRANSIENT_SQL_STATES = {
    "40001",  # serialization_failure
    "40P01",  # deadlock_detected
    "08000",  # connection_exception
    "08003",  # connection_does_not_exist
    "08006",  # connection_failure
    "57P01",  # admin_shutdown
    "57P02",  # crash_shutdown
    "57P03",  # cannot_connect_now
}


def is_transient_db_error(exc: Exception) -> bool:
    """Determines whether a database exception is transient and safe to retry."""
    if isinstance(exc, (ConnectionResetError, TimeoutError, asyncio.TimeoutError)):
        return True

    if isinstance(exc, (OperationalError, InterfaceError)):
        return True

    if isinstance(exc, DBAPIError) and exc.orig:
        orig = exc.orig
        # Check pgcode or sqlstate if present
        sqlstate = getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)
        if sqlstate and str(sqlstate) in TRANSIENT_SQL_STATES:
            return True
        error_msg = str(orig).lower()
        if any(term in error_msg for term in ["deadlock", "lock timeout", "connection reset", "server closed the connection", "broken pipe"]):
            return True

    return False


async def execute_with_retry(
    operation: Callable[..., Any],
    *args,
    max_retries: int = 3,
    initial_delay: float = 0.05,
    backoff_multiplier: float = 2.0,
    max_delay: float = 2.0,
    **kwargs
) -> Any:
    """Executes an async database operation with automatic retries on transient errors."""
    attempt = 0
    current_delay = initial_delay

    while True:
        try:
            return await operation(*args, **kwargs)
        except Exception as exc:
            attempt += 1
            if attempt > max_retries or not is_transient_db_error(exc):
                raise exc

            # Compute exponential backoff with jitter
            jitter = random.uniform(0.5, 1.5)
            sleep_time = min(max_delay, current_delay * jitter)
            logger.warning(
                "Transient database error on attempt %d/%d (%s). Retrying in %.3fs...",
                attempt, max_retries, exc, sleep_time
            )
            await asyncio.sleep(sleep_time)
            current_delay *= backoff_multiplier
