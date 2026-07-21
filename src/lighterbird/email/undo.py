"""Deferred email operation with undo support.

Provides a thread-safe in-memory registry for pending email operations
(trash, hard-delete, spam, fraud) that can be reverted within a configurable
time window.  After the window expires, the IMAP backlog entries are enqueued
and the operation becomes permanent.

Usage::

    mgr = UndoRegistry(email_svc)

    # Schedule a trash operation with 5-second undo window
    op_id = mgr.schedule(
        action="trash",
        msg_uuid=msg["uuid"],
        account_email=msg["account_email"],
        folder_name=msg["folder_name"],
        imap_uid=msg["imap_uid"],
        payload={"some_metadata": "value"},
        delay=5.0,
    )

    # Revert within the window
    mgr.undo(op_id)

    # Timer fires after 5s → backlog enqueued automatically.
"""

from __future__ import annotations

import logging
import threading
import uuid as uuid_mod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Phantom type for operation IDs
UndoOpId = str


class UndoError(Exception):
    """Raised when an undo operation cannot be completed."""


@dataclass
class UndoOperation:
    """A pending email operation that can be reverted.

    Attributes:
        op_id: Unique operation identifier.
        action: One of ``"trash"``, ``"hard_delete"``, ``"spam"``, ``"fraud"``.
        msg_uuid: The message UUID that was acted on.
        account_email: Account the message belongs to.
        folder_name: Original folder name (for undo revert).
        imap_uid: Original IMAP UID (for undo revert).
        payload: Arbitrary metadata captured at schedule time.
        created_at: When the operation was scheduled.
        delay: Time window in seconds before commit.
        timer: Active ``threading.Timer`` or ``None`` after commit/cancel.
        committed: ``True`` if the timer has fired and IMAP ops were enqueued.
        reverted: ``True`` if the operation was undone before commit.
        revert_cb: Callback to revert local DB state (set on schedule).
        commit_cb: Callback to enqueue IMAP backlog (set on schedule).
    """
    op_id: str
    action: str
    msg_uuid: str
    account_email: str
    folder_name: str | None
    imap_uid: int | None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    delay: float = 5.0
    timer: threading.Timer | None = None
    committed: bool = False
    reverted: bool = False
    revert_cb: Callable[[], None] | None = None
    commit_cb: Callable[[], None] | None = None


class UndoRegistry:
    """Thread-safe, in-memory registry of undoable email operations.

    Operations are stored in a dict keyed by ``op_id``. Each operation
    has a timer that, unless cancelled, commits it (enqueues IMAP backlog)
    after *delay* seconds.
    """

    def __init__(self) -> None:
        self._ops: dict[str, UndoOperation] = {}
        self._lock = threading.Lock()

    # ── Public API ──────────────────────────────────────────────────────

    def schedule(
        self,
        action: str,
        msg_uuid: str,
        account_email: str,
        folder_name: str | None,
        imap_uid: int | None,
        payload: dict[str, Any] | None = None,
        delay: float = 5.0,
    ) -> str:
        """Schedule a deferred email operation with undo support.

        The local DB change must already have been applied before calling
        this method.  The *revert_cb* and *commit_cb* are set later via
        :meth:`set_callbacks`.

        Returns:
            The operation ID (UUID string).
        """
        op_id = uuid_mod.uuid4().hex
        op = UndoOperation(
            op_id=op_id,
            action=action,
            msg_uuid=msg_uuid,
            account_email=account_email,
            folder_name=folder_name,
            imap_uid=imap_uid,
            payload=payload or {},
            created_at=datetime.now(UTC).isoformat(),
            delay=delay,
        )
        with self._lock:
            self._ops[op_id] = op
        logger.debug(
            "undo: scheduled %s for msg %s (op=%s, delay=%ss)",
            action, msg_uuid[:8], op_id[:8], delay,
        )
        return op_id

    def set_callbacks(
        self,
        op_id: str,
        revert_cb: Callable[[], None],
        commit_cb: Callable[[], None],
    ) -> None:
        """Attach revert and commit callbacks, then start the timer.

        Must be called once after :meth:`schedule` and before any undo/expiry
        call.  Starting the timer here (rather than in :meth:`schedule`)
        ensures the callbacks are in place before the timer can fire.
        """
        with self._lock:
            op = self._ops.get(op_id)
            if op is None:
                raise UndoError(f"Operation not found: {op_id[:8]}")
            if op.timer is not None:
                raise UndoError(f"Timer already started for op {op_id[:8]}")
            op.revert_cb = revert_cb
            op.commit_cb = commit_cb
            op.timer = threading.Timer(op.delay, self._commit, args=[op_id])
            op.timer.daemon = True
            op.timer.start()

    def undo(self, op_id: str) -> None:
        """Revert a pending operation before its timer fires.

        If the operation has already been committed, raises ``UndoError``.
        If it has already been reverted, this is a no-op.
        """
        with self._lock:
            op = self._ops.get(op_id)
            if op is None:
                raise UndoError(f"Operation not found: {op_id[:8]}")
            if op.committed:
                raise UndoError(
                    f"Cannot undo op {op_id[:8]}: already committed"
                )
            if op.reverted:
                logger.debug("undo: op %s already reverted, skipping", op_id[:8])
                return
            op.reverted = True
            if op.timer:
                op.timer.cancel()
                op.timer = None
            revert = op.revert_cb

        # Execute revert outside the lock to avoid deadlocks
        if revert:
            try:
                revert()
            except Exception:
                logger.exception("undo: revert failed for op %s", op_id[:8])
                raise

        # Clean up
        with self._lock:
            self._ops.pop(op_id, None)

        logger.info("undo: reverted %s for msg %s", op.action, op.msg_uuid[:8])

    def get(self, op_id: str) -> UndoOperation | None:
        """Look up an operation by ID without modifying it."""
        with self._lock:
            return self._ops.get(op_id)

    def cleanup(self) -> None:
        """Cancel all pending operations (called during shutdown)."""
        with self._lock:
            for op_id, op in list(self._ops.items()):
                if op.timer and not op.committed and not op.reverted:
                    op.timer.cancel()
                logger.debug(
                    "undo: cleaned up op %s (%s)",
                    op_id[:8], op.action,
                )
            self._ops.clear()

    # ── Internal ─────────────────────────────────────────────────────────

    def _commit(self, op_id: str) -> None:
        """Timer callback: enqueue IMAP backlog entries."""
        with self._lock:
            op = self._ops.get(op_id)
            if op is None or op.reverted:
                return
            op.committed = True
            op.timer = None
            commit = op.commit_cb
            op_data = dict(op.payload) if op.payload else {}

        if commit:
            try:
                commit()
            except Exception:
                logger.exception(
                    "undo: commit failed for op %s (%s)",
                    op_id[:8], op.action,
                )

        # Clean up after commit
        with self._lock:
            self._ops.pop(op_id, None)

        logger.info(
            "undo: committed %s for msg %s",
            op.action, (op_data.get("msg_uuid", "") or "")[:8],
        )


# ── Module-level singleton ─────────────────────────────────────────────

_registry: UndoRegistry | None = None
_registry_lock = threading.Lock()


def get_undo_registry() -> UndoRegistry:
    """Get or create the singleton undo registry instance."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = UndoRegistry()
    return _registry


def reset_undo_registry() -> None:
    """Reset the singleton (for testing)."""
    global _registry
    with _registry_lock:
        if _registry is not None:
            _registry.cleanup()
        _registry = None
