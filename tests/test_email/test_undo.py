"""Tests for the email undo scheduler (lighterbird.email.undo)."""

from __future__ import annotations

import time

import pytest

from lighterbird.email.undo import UndoRegistry, get_undo_registry, reset_undo_registry


class TestUndoRegistry:
    """Unit tests for UndoRegistry."""

    def setup_method(self):
        reset_undo_registry()

    def test_schedule_returns_op_id(self):
        """schedule() returns a non-empty operation ID."""
        registry = UndoRegistry()
        op_id = registry.schedule("trash", "msg-uuid-1", "a@b.com", "INBOX", 123)
        assert op_id
        assert isinstance(op_id, str)
        assert len(op_id) > 8

    def test_get_returns_op(self):
        """get() returns the operation before commit/revert."""
        registry = UndoRegistry()
        op_id = registry.schedule("trash", "msg-uuid-1", "a@b.com", "INBOX", 123)
        op = registry.get(op_id)
        assert op is not None
        assert op.action == "trash"
        assert op.msg_uuid == "msg-uuid-1"
        assert op.account_email == "a@b.com"

    def test_get_returns_none_for_unknown(self):
        """get() returns None for a non-existent operation ID."""
        registry = UndoRegistry()
        assert registry.get("nonexistent") is None

    def test_undo_reverts_before_timer_expiry(self):
        """undo() calls the revert callback and cleans up before timer fires."""
        registry = UndoRegistry()
        op_id = registry.schedule("trash", "msg-uuid-1", "a@b.com", "INBOX", 123)

        reverted = []
        committed = []

        registry.set_callbacks(
            op_id,
            revert_cb=lambda: reverted.append("called"),
            commit_cb=lambda: committed.append("called"),
        )

        # Undo immediately (before the 5s timer fires)
        registry.undo(op_id)

        assert reverted == ["called"]
        assert committed == []  # commit should NOT have been called
        assert registry.get(op_id) is None  # cleaned up

    def test_commit_fires_after_delay(self):
        """The commit callback fires after the configured delay."""
        registry = UndoRegistry()
        op_id = registry.schedule("trash", "msg-uuid-1", "a@b.com", "INBOX", 123, delay=0.05)

        committed = []

        registry.set_callbacks(
            op_id,
            revert_cb=lambda: None,
            commit_cb=lambda: committed.append("called"),
        )

        # Wait for timer to fire
        time.sleep(0.2)

        assert committed == ["called"]
        assert registry.get(op_id) is None  # cleaned up after commit

    def test_undo_after_commit_is_silent(self):
        """undo() on an already-committed operation is silent (op already cleaned up)."""
        registry = UndoRegistry()
        op_id = registry.schedule("trash", "msg-uuid-1", "a@b.com", "INBOX", 123, delay=0.05)

        committed = []

        registry.set_callbacks(
            op_id,
            revert_cb=lambda: None,
            commit_cb=lambda: committed.append("called"),
        )

        # Wait for commit (cleans up the op)
        time.sleep(0.2)
        assert committed == ["called"]
        assert registry.get(op_id) is None

        # Now try to undo — op no longer exists, should raise UndoError
        with pytest.raises(Exception, match="not found"):
            registry.undo(op_id)

    def test_double_undo_raises_for_already_cleaned_up(self):
        """undo() on an already-reverted operation raises UndoError (cleaned up)."""
        registry = UndoRegistry()
        op_id = registry.schedule("trash", "msg-uuid-1", "a@b.com", "INBOX", 123)

        call_count = []

        registry.set_callbacks(
            op_id,
            revert_cb=lambda: call_count.append("called"),
            commit_cb=lambda: None,
        )

        registry.undo(op_id)
        assert len(call_count) == 1

        # Second undo should raise since the op was cleaned up
        with pytest.raises(Exception, match="not found"):
            registry.undo(op_id)

    def test_cleanup_cancels_pending_timers(self):
        """cleanup() cancels all pending timers without calling commit."""
        registry = UndoRegistry()
        op_id = registry.schedule("trash", "msg-uuid-1", "a@b.com", "INBOX", 123)

        committed = []

        registry.set_callbacks(
            op_id,
            revert_cb=lambda: None,
            commit_cb=lambda: committed.append("called"),
        )

        registry.cleanup()
        assert committed == []  # commit should NOT have fired
        assert registry.get(op_id) is None  # cleaned up

    def test_singleton_is_shared(self):
        """get_undo_registry() returns the same instance."""
        r1 = get_undo_registry()
        r2 = get_undo_registry()
        assert r1 is r2

    def test_reset_creates_new_singleton(self):
        """reset_undo_registry() creates a fresh singleton."""
        r1 = get_undo_registry()
        reset_undo_registry()
        r2 = get_undo_registry()
        assert r1 is not r2


class TestUndoWithShortDelay:
    """Integration-style tests with a real (short) timer."""

    def test_set_callbacks_starts_timer(self):
        """The timer starts only after set_callbacks is called."""
        registry = UndoRegistry()
        op_id = registry.schedule("trash", "msg-uuid-1", "a@b.com", "INBOX", 123, delay=0.1)

        committed = []

        # Timer should NOT be running yet
        op = registry.get(op_id)
        assert op is not None
        assert op.timer is None  # timer not started

        registry.set_callbacks(
            op_id,
            revert_cb=lambda: None,
            commit_cb=lambda: committed.append("called"),
        )

        # Now timer should be running
        op = registry.get(op_id)
        assert op is not None
        assert op.timer is not None

        # Wait for it to fire
        time.sleep(0.2)
        assert committed == ["called"]

    def test_undo_before_set_callbacks_undo(self):
        """undo() before set_callbacks still cleans up the operation."""
        registry = UndoRegistry()
        op_id = registry.schedule("trash", "msg-uuid-1", "a@b.com", "INBOX", 123)

        # undoing before set_callbacks still works — reverts without callbacks,
        # then cleans up
        registry.undo(op_id)
        assert registry.get(op_id) is None
