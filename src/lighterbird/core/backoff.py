"""Exponential backoff utility for retryable operations.

Shared by email send queue and calendar sync queue.
"""

from __future__ import annotations


def compute_backoff_seconds(
    retries: int,
    base_seconds: int = 60,
    max_seconds: int = 86400,
) -> int:
    """Compute the next backoff delay in seconds using exponential backoff.

    Formula: ``delay = min(base * 2^retries, max)``

    Args:
        retries: Number of retries already attempted (0 = first retry).
        base_seconds: Base delay in seconds (default 60 = 1 minute).
        max_seconds: Maximum delay in seconds (default 86400 = 24 hours).

    Returns:
        Delay in seconds before the next attempt.
    """
    delay = base_seconds * (2**retries)
    return min(delay, max_seconds)


__all__ = ["compute_backoff_seconds"]
