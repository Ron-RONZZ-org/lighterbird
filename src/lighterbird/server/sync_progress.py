"""Sync progress tracking — thread-safe in-memory progress store.

Provides ``SyncProgressTracker`` which stores sync progress keyed by
task UUID.  The tracker is thread-safe (uses a ``threading.Lock``) so
it can be shared between the FastAPI request thread and a background
sync thread.

Usage::

    tracker = SyncProgressTracker()
    task_id = tracker.start("user@example.com")
    # Pass tracker to sync_account in a background thread:
    thread = threading.Thread(
        target=email_svc.sync_account, args=(...),
        kwargs={"progress_tracker": tracker},
    )
    thread.start()
    # Frontend polls GET /api/v1/email/sync/progress/{task_id}
    ...
    progress = tracker.get(task_id)  # {"status": "running", ...}
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal


@dataclass
class SyncProgress:
    """Progress of a single sync task."""

    task_id: str
    account_email: str
    status: Literal["running", "complete", "error"]
    started_at: str
    completed_at: str | None = None

    # Folder progress
    total_folders: int = 0
    current_folder: int = 0
    folder_name: str = ""

    # Message progress
    total_messages: int = 0
    new_messages: int = 0

    # Result (when complete)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "account_email": self.account_email,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_folders": self.total_folders,
            "current_folder": self.current_folder,
            "folder_name": self.folder_name,
            "total_messages": self.total_messages,
            "new_messages": self.new_messages,
            "errors": self.errors,
        }


class SyncProgressTracker:
    """Thread-safe in-memory sync progress store.

    Progress entries are created by :meth:`start` and updated via
    :meth:`update_folder` and :meth:`complete` / :meth:`fail`.
    Stale entries (older than 5 minutes after completion) are
    cleaned up lazily on each :meth:`start` call.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, SyncProgress] = {}

    def start(self, account_email: str) -> str:
        """Register a new sync task and return its task_id."""
        self._cleanup_stale()
        task_id = uuid.uuid4().hex
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._tasks[task_id] = SyncProgress(
                task_id=task_id,
                account_email=account_email,
                status="running",
                started_at=now,
            )
        return task_id

    def set_total_folders(self, task_id: str, total: int) -> None:
        """Set the total number of folders to sync."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.total_folders = total

    def update_folder(self, task_id: str, current: int, name: str,
                      total_messages: int = 0, new_messages: int = 0) -> None:
        """Update folder-level progress."""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.current_folder = current
                task.folder_name = name
                task.total_messages += total_messages
                task.new_messages += new_messages

    def complete(self, task_id: str, result_total: int = 0,
                 result_new: int = 0, errors: list[str] | None = None) -> None:
        """Mark a sync task as complete."""
        now = datetime.now(UTC).isoformat()
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = "complete"
                task.completed_at = now
                task.total_messages = result_total
                task.new_messages = result_new
                if errors:
                    task.errors = errors

    def fail(self, task_id: str, error: str) -> None:
        """Mark a sync task as failed."""
        now = datetime.now(UTC).isoformat()
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = "error"
                task.completed_at = now
                task.errors.append(error)

    def get(self, task_id: str) -> dict | None:
        """Get progress for a task, or None if unknown."""
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_dict() if task else None

    def _cleanup_stale(self) -> None:
        """Remove tasks that completed >5 minutes ago."""
        now = datetime.now(UTC)
        stale_ids: list[str] = []
        with self._lock:
            for tid, task in self._tasks.items():
                if task.status in ("complete", "error") and task.completed_at:
                    completed = datetime.fromisoformat(task.completed_at)
                    if (now - completed).total_seconds() > 300:
                        stale_ids.append(tid)
            for tid in stale_ids:
                del self._tasks[tid]


# ── Module-level singleton ──────────────────────────────────────────────

_tracker: SyncProgressTracker | None = None
_tracker_lock = threading.Lock()


def get_sync_progress_tracker() -> SyncProgressTracker:
    """Get the application-wide sync progress tracker singleton."""
    global _tracker
    if _tracker is None:
        with _tracker_lock:
            if _tracker is None:
                _tracker = SyncProgressTracker()
    return _tracker
