"""Background worker with thread-safe job queue and FastAPI lifespan integration.

Provides a lightweight, single-threaded worker pattern for async tasks
like email sync, CalDAV push, and periodic polling. Designed for
``FastAPI.lifespan`` integration.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Job:
    """A unit of work for the background worker.

    Attributes:
        domain: Logical domain name (``"email"``, ``"caldav"``).
        operation: Operation type (``"sync_account"``, ``"push_event"``).
        payload: Arbitrary JSON-serializable data.
        on_error: Optional callback invoked if processing raises.
    """

    domain: str
    operation: str
    payload: dict[str, Any] = field(default_factory=dict)
    on_error: Callable[[Exception], None] | None = None


class BackgroundWorker:
    """Single-threaded background worker consuming jobs from a queue.

    Design rationale:
        - A single consumer thread avoids SQLite write contention
          (only one thread writes to each .db at a time).
        - ``queue.Queue`` provides a thread-safe producer/consumer
          boundary — the FastAPI route handlers enqueue jobs, the
          worker thread executes them.
        - Daemon threads are terminated on process exit, but clean
          shutdown via :meth:`stop()` is preferred to flush active work.

    Usage::

        worker = BackgroundWorker("email-sync")
        worker.start()
        worker.enqueue(Job("email", "sync", {"account_uuid": "..."}))
        # ...
        worker.stop()
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._queue: queue.Queue[Job | None] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the worker thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("[%s] Worker already running", self.name)
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=self.name,
            daemon=True,
        )
        self._thread.start()
        logger.info("[%s] Worker started", self.name)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the worker to stop and wait for it to finish.

        Args:
            timeout: Max seconds to wait for the current job to finish.
        """
        self._stop_event.set()
        self._queue.put(None)  # unblock the worker if it's waiting
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning(
                    "[%s] Worker did not stop within %.1fs timeout",
                    self.name,
                    timeout,
                )
            else:
                logger.info("[%s] Worker stopped cleanly", self.name)

    @property
    def is_alive(self) -> bool:
        """Check whether the worker thread is currently running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def queue_size(self) -> int:
        """Approximate number of pending jobs."""
        return self._queue.qsize()

    # ── Job management ─────────────────────────────────────────────────────

    def enqueue(self, job: Job) -> None:
        """Add a job to the work queue (thread-safe).

        Args:
            job: The job to process.
        """
        self._queue.put(job)

    # ── Internal loop ──────────────────────────────────────────────────────

    def _run(self) -> None:
        """Main worker loop — pulls jobs from the queue and processes them.

        Never raises: all exceptions are caught, logged, and routed to
        the job's ``on_error`` callback if provided.
        """
        logger.info("[%s] Worker loop started", self.name)
        while not self._stop_event.is_set():
            try:
                job = self._queue.get(timeout=1.0)
                if job is None:
                    break  # sentinel received
                self._process(job)
            except queue.Empty:
                continue
            except Exception as exc:
                logger.error(
                    "[%s] Unexpected error in worker loop: %s",
                    self.name,
                    exc,
                    exc_info=True,
                )
        logger.info("[%s] Worker loop exited", self.name)

    def _process(self, job: Job) -> None:
        """Execute a single job, catching and reporting errors.

        Args:
            job: The job to process.
        """
        logger.info(
            "[%s] Processing job: %s/%s",
            self.name,
            job.domain,
            job.operation,
        )
        try:
            self.execute_job(job)
        except Exception as exc:
            logger.error(
                "[%s] Job %s/%s failed: %s",
                self.name,
                job.domain,
                job.operation,
                exc,
                exc_info=True,
            )
            if job.on_error:
                try:
                    job.on_error(exc)
                except Exception as cb_err:
                    logger.error(
                        "[%s] on_error callback raised: %s",
                        self.name,
                        cb_err,
                    )

    def execute_job(self, job: Job) -> None:
        """Override this in a subclass to handle domain-specific jobs.

        The default implementation logs the job and does nothing.

        Args:
            job: The job to execute.
        """
        logger.debug(
            "[%s] No handler for job: %s/%s (payload=%s)",
            self.name,
            job.domain,
            job.operation,
            job.payload,
        )


# ── Convenience: multiple workers managed together ────────────────────────


class WorkerPool:
    """Manage a group of :class:`BackgroundWorker` instances together.

    Usage::

        pool = WorkerPool()
        pool.add("email", BackgroundWorker("email-sync"))
        pool.add("caldav", BackgroundWorker("caldav-sync"))
        pool.start_all()
        # ...
        pool.stop_all(timeout=5.0)
    """

    def __init__(self) -> None:
        self._workers: dict[str, BackgroundWorker] = {}

    def add(self, name: str, worker: BackgroundWorker) -> None:
        """Register a named worker."""
        self._workers[name] = worker

    def get(self, name: str) -> BackgroundWorker | None:
        """Get a registered worker by name."""
        return self._workers.get(name)

    def start_all(self) -> None:
        """Start all registered workers."""
        for _name, w in self._workers.items():
            w.start()

    def stop_all(self, timeout: float = 5.0) -> None:
        """Stop all registered workers."""
        for name, w in self._workers.items():
            logger.info("[pool] Stopping worker: %s", name)
            w.stop(timeout=timeout)

    @property
    def status(self) -> dict[str, bool]:
        """Return a dict mapping worker name → is_alive."""
        return {n: w.is_alive for n, w in self._workers.items()}


__all__ = [
    "BackgroundWorker",
    "Job",
    "WorkerPool",
]
