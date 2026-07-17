"""Tests for SyncStateManager — per-account sync state tracking."""

from __future__ import annotations

from lighterbird.server.sync_state import SyncStateManager


class TestSyncStateManager:
    """Unit tests for the SyncStateManager class."""

    def test_register_and_get_state(self):
        mgr = SyncStateManager()
        mgr.register_account("user@example.com")

        state = mgr.get_state("user@example.com")
        assert state is not None
        assert state["account_email"] == "user@example.com"
        assert state["status"] == "startup-syncing"

    def test_register_and_get_unknown(self):
        mgr = SyncStateManager()
        assert mgr.get_state("unknown@example.com") is None

    def test_set_status(self):
        mgr = SyncStateManager()
        mgr.register_account("user@example.com")
        mgr.set_status("user@example.com", "idle")

        state = mgr.get_state("user@example.com")
        assert state["status"] == "idle"

    def test_set_status_with_error(self):
        mgr = SyncStateManager()
        mgr.register_account("user@example.com")
        mgr.set_status("user@example.com", "error", error="Connection refused")

        state = mgr.get_state("user@example.com")
        assert state["status"] == "error"
        assert state["last_error"] == "Connection refused"

    def test_startup_completed_empty(self):
        """No accounts → startup is trivially complete."""
        mgr = SyncStateManager()
        assert mgr.startup_completed is True

    def test_startup_not_completed_while_syncing(self):
        mgr = SyncStateManager()
        mgr.register_account("user@example.com")

        # Startup not completed while in startup-syncing
        assert mgr.startup_completed is False

    def test_startup_completed_after_sync(self):
        mgr = SyncStateManager()
        mgr.register_account("user@example.com")
        mgr.set_status("user@example.com", "idle")

        assert mgr.startup_completed is True

    def test_startup_completed_partial(self):
        """One account done, one still syncing → not completed."""
        mgr = SyncStateManager()
        mgr.register_account("alice@example.com")
        mgr.register_account("bob@example.com")
        mgr.set_status("alice@example.com", "idle")

        assert mgr.startup_completed is False

    def test_startup_completed_all_done(self):
        mgr = SyncStateManager()
        mgr.register_account("alice@example.com")
        mgr.register_account("bob@example.com")
        mgr.set_status("alice@example.com", "idle")
        mgr.set_status("bob@example.com", "error")

        assert mgr.startup_completed is True

    def test_set_status_implicitly_creates_state(self):
        """set_status without register_account creates state automatically."""
        mgr = SyncStateManager()
        mgr.set_status("new@example.com", "idle")

        state = mgr.get_state("new@example.com")
        assert state is not None
        assert state["status"] == "idle"

    def test_remove_account(self):
        mgr = SyncStateManager()
        mgr.register_account("user@example.com")
        mgr.remove_account("user@example.com")

        assert mgr.get_state("user@example.com") is None

    def test_set_idle_heartbeat(self):
        mgr = SyncStateManager()
        mgr.register_account("user@example.com")
        mgr.set_idle_heartbeat("user@example.com")

        state = mgr.get_state("user@example.com")
        assert state["last_idle_heartbeat"] is not None
        assert state["reconnects"] == 0

    def test_set_idle_status(self):
        mgr = SyncStateManager()
        mgr.register_account("user@example.com")
        mgr.set_idle_status("user@example.com", alive=True, supported=True)

        state = mgr.get_state("user@example.com")
        assert state["idle_alive"] is True
        assert state["idle_supported"] is True

    def test_set_last_sync(self):
        mgr = SyncStateManager()
        mgr.register_account("user@example.com")
        mgr.set_last_sync("user@example.com")

        state = mgr.get_state("user@example.com")
        assert state["last_sync_at"] is not None

    def test_all_states(self):
        mgr = SyncStateManager()
        mgr.register_account("alice@example.com")
        mgr.register_account("bob@example.com")

        states = mgr.all_states()
        assert len(states) == 2

    def test_on_startup_complete_fires_immediately_if_done(self):
        """Callback fires immediately if startup already complete."""
        mgr = SyncStateManager()
        mgr.register_account("user@example.com")
        mgr.set_status("user@example.com", "idle")

        fired = []
        mgr.on_startup_complete(lambda: fired.append(True))
        assert len(fired) == 1

    def test_on_startup_complete_fires_after_transition(self):
        """Callback fires when last account completes startup."""
        mgr = SyncStateManager()
        mgr.register_account("user@example.com")

        fired = []
        mgr.on_startup_complete(lambda: fired.append(True))
        assert len(fired) == 0  # Not yet

        mgr.set_status("user@example.com", "idle")
        assert len(fired) == 1

    def test_multiple_accounts_separate_states(self):
        """Account states are independent."""
        mgr = SyncStateManager()
        mgr.register_account("alice@example.com")
        mgr.register_account("bob@example.com")

        mgr.set_status("alice@example.com", "idle")
        mgr.set_status("bob@example.com", "error")

        alice = mgr.get_state("alice@example.com")
        bob = mgr.get_state("bob@example.com")
        assert alice["status"] == "idle"
        assert bob["status"] == "error"
