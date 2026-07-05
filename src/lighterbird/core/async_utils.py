"""Utilities for running async code from sync contexts.

Fixes the ``asyncio.run()`` problem: when a sync handler inside an async
application (e.g. FastAPI/uvicorn) needs to call an async function,
``asyncio.run()`` raises ``RuntimeError`` because an event loop is already
running in the current thread.

This module provides a safe, thread-based workaround.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Callable


def run_async_sync(coro_factory: Callable[[], Any], timeout: float | None = None) -> Any:
    """Run an async coroutine from a sync context safely.

    Spawns the coroutine in a **separate thread with its own event loop**,
    avoiding the ``asyncio.run()`` restriction of "cannot be called from a
    running event loop in the same thread".

    Args:
        coro_factory: A zero-argument callable that returns a coroutine.
            Using a factory (``lambda: fn(...)``) ensures the coroutine is
            created inside the target thread, not the caller thread.
        timeout: Optional timeout in seconds for the thread.

    Returns:
        The return value of the coroutine.

    Raises:
        Any exception raised by the coroutine is re-raised in the caller
        thread.
    """
    result: Any = None
    exc: BaseException | None = None

    def _inner() -> None:
        nonlocal result, exc
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(coro_factory())
        except BaseException as e:
            exc = e
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_inner)
        return future.result(timeout=timeout)


__all__ = [
    "run_async_sync",
]
