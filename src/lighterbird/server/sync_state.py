"""Per-account sync state tracking — thread-safe singleton.

Tracks whether the initial startup sync has completed for each account,
the current status (startup-syncing, idle, syncing, etc.), and IDLE
thread health.  Used by the backend to orchestrate startup sync and by
the frontend to display sync status.

Usage::

    state_mgr = get_sync_state_manager()
    state_mgr.set_status("user@example.com", "idle")
    if state_mgr.startup_completed:
        ...
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal


SyncStatus = Literal[
    "startup-syncing",  # Initial startup sync in progress
    "idle",             # IDLE thread running, listening for push
    "syncing",          # Manual or notification-triggered sync running
    "error",            # Last sync or IDLE attempt failed
    "disconnected",     # IDLE thread disconnected, reconnecting
    "disabled",         # No password or server doesn't support IDLE
]


@dataclass
class AccountSyncState:
    """Sync state for a single email account."""

    account_email: str
    status: SyncStatus = "startup-syncing"
    last_sync_at: str | None = None
    last_error: str | None = None

    # IDLE thread health
    idle_alive: bool = False
    idle_supported: bool | None = None  # None = not yet detected
    last_idle_heartbeat: str | None = None
    reconnects: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_email": self.account_email,
            "status": self.status,
            "last_sync_at": self.last_sync_at,
            "last_error": self.last_error,
            "idle_alive": self.idle_alive,
            "idle_supported": self.idle_supported,
            "last_idle_heartbeat": self.last_idle_heartbeat,
            "reconnects": self.reconnects,
        }


class SyncStateManager:
    """Thread-safe singleton tracking per-account sync state.

    Unlike :class:`~lighterbird.server.sync_progress.SyncProgressTracker`
    which is task-scoped (ephemeral, per-sync-task), this is account-scoped
    and persists across the application lifecycle.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, AccountSyncState] = {}
        self._startup_syncing: set[str] = set()
        self._startup_complete_callbacks: list[callable] = []

    # ── Account lifecycle ──────────────────────────────────────────────

    def register_account(self, account_email: str) -> None:
        """Register a new account (called on account creation)."""
        with self._lock:
            self._states[account_email] = AccountSyncState(
                account_email=account_email,
            )
            self._startup_syncing.add(account_email)

    def remove_account(self, account_email: str) -> None:
        """Remove an account's state (called on account deletion)."""
        with self._lock:
            self._states.pop(account_email, None)
            self._startup_syncing.discard(account_email)

    # ── Status transitions ─────────────────────────────────────────────

    def set_status(self, account_email: str, status: SyncStatus,
                   error: str | None = None) -> None:
        """Update the status for an account.

        Automatically tracks startup completion:
        - When an account transitions from ``startup-syncing`` to any
          non-startup status, it is marked as startup-complete.
        - When all accounts are startup-complete, callbacks fire.
        """
        with self._lock:
            state = self._states.get(account_email)
            if state is None:
                state = AccountSyncState(account_email=account_email)
                self._states[account_email] = state
            state.status = status
            if status == "syncing":
                self._startup_syncing.discard(account_email)
            if error is not None:
                state.last_error = error
            if status == "idle":
                state.last_error = None

            # Track startup sync completion
            if account_email in self._startup_syncing and status != "startup-syncing":
                self._startup_syncing.discard(account_email)
                state.last_sync_at = datetime.now(UTC).isoformat()

            # Fire callbacks if all accounts done with startup
            if not self._startup_syncing and self._states:
                self._fire_startup_complete()

    def set_idle_heartbeat(self, account_email: str) -> None:
        """Update the last IDLE heartbeat timestamp."""
        with self._lock:
            state = self._states.get(account_email)
            if state:
                state.last_idle_heartbeat = datetime.now(UTC).isoformat()
                state.reconnects = 0

    def set_idle_status(self, account_email: str, alive: bool,
                        supported: bool | None = None) -> None:
        """Update IDLE thread health for an account."""
        with self._lock:
            state = self._states.get(account_email)
            if state:
                state.idle_alive = alive
                if supported is not None:
                    state.idle_supported = supported

    def set_last_sync(self, account_email: str) -> None:
        """Update the last sync timestamp."""
        with self._lock:
            state = self._states.get(account_email)
            if state:
                state.last_sync_at = datetime.now(UTC).isoformat()

    # ── Queries ────────────────────────────────────────────────────────

    @property
    def startup_completed(self) -> bool:
        """True when all registered accounts have completed startup sync."""
        with self._lock:
            if not self._states:
                return True  # No accounts = trivially complete
            return len(self._startup_syncing) == 0

    def get_state(self, account_email: str) -> dict[str, Any] | None:
        """Get the sync state dict for an account, or None."""
        with self._lock:
            state = self._states.get(account_email)
            return state.to_dict() if state else None

    def all_states(self) -> list[dict[str, Any]]:
        """Get sync state dicts for all registered accounts."""
        with self._lock:
            return [s.to_dict() for s in self._states.values()]

    # ── Startup complete callbacks ─────────────────────────────────────

    def on_startup_complete(self, callback: callable) -> None:
        """Register a callback fired when all accounts complete startup.

        The callback is called with no arguments.  If startup is already
        complete when this is called, the callback fires immediately.
        """
        with self._lock:
            if not self._startup_syncing and self._states:
                callback()
            else:
                self._startup_complete_callbacks.append(callback)

    def _fire_startup_complete(self) -> None:
        """Fire all registered startup-complete callbacks."""
        callbacks = list(self._startup_complete_callbacks)
        self._startup_complete_callbacks.clear()
        for cb in callbacks:
            try:
                cb()
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "Startup complete callback failed"
                )


# ── Module-level singleton ──────────────────────────────────────────────

_state_manager: SyncStateManager | None = None
_state_manager_lock = threading.Lock()


def get_sync_state_manager() -> SyncStateManager:
    """Get the application-wide SyncStateManager singleton."""
    global _state_manager
    if _state_manager is None:
        with _state_manager_lock:
            if _state_manager is None:
                _state_manager = SyncStateManager()
    return _state_manager


def init_sync_state_manager() -> SyncStateManager:
    """Initialise (or reinitialise) the SyncStateManager.

    Called from server startup to reset state.
    """
    global _state_manager
    with _state_manager_lock:
        _state_manager = SyncStateManager()
        return _state_manager


__all__ = [
    "AccountSyncState",
    "SyncStateManager",
    "get_sync_state_manager",
    "init_sync_state_manager",
]
