"""Tests for sync progress tracker + API endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app
from lighterbird.server.sync_progress import SyncProgressTracker


class TestSyncProgressTracker:
    """Unit tests for the SyncProgressTracker class."""

    def test_start_creates_task(self):
        tracker = SyncProgressTracker()
        task_id = tracker.start("user@example.com")
        assert task_id is not None
        assert len(task_id) > 0

        progress = tracker.get(task_id)
        assert progress is not None
        assert progress["task_id"] == task_id
        assert progress["account_email"] == "user@example.com"
        assert progress["status"] == "running"
        assert progress["started_at"] is not None
        assert progress["completed_at"] is None

    def test_update_folder_tracks_progress(self):
        tracker = SyncProgressTracker()
        task_id = tracker.start("user@example.com")
        tracker.set_total_folders(task_id, 10)
        tracker.update_folder(task_id, 3, "INBOX", total_messages=50, new_messages=5)

        progress = tracker.get(task_id)
        assert progress["total_folders"] == 10
        assert progress["current_folder"] == 3
        assert progress["folder_name"] == "INBOX"
        assert progress["total_messages"] == 50
        assert progress["new_messages"] == 5

    def test_complete_marks_status(self):
        tracker = SyncProgressTracker()
        task_id = tracker.start("user@example.com")
        tracker.complete(task_id, result_total=100, result_new=10,
                         errors=["warning 1"])

        progress = tracker.get(task_id)
        assert progress["status"] == "complete"
        assert progress["completed_at"] is not None
        assert progress["total_messages"] == 100
        assert progress["new_messages"] == 10
        assert progress["errors"] == ["warning 1"]

    def test_fail_marks_error(self):
        tracker = SyncProgressTracker()
        task_id = tracker.start("user@example.com")
        tracker.fail(task_id, "Connection refused")

        progress = tracker.get(task_id)
        assert progress["status"] == "error"
        assert progress["completed_at"] is not None
        assert "Connection refused" in progress["errors"]

    def test_get_unknown_task_returns_none(self):
        tracker = SyncProgressTracker()
        assert tracker.get("nonexistent-task-id") is None

    def test_cleanup_stale_removes_old_completed_tasks(self):
        tracker = SyncProgressTracker()
        task_id = tracker.start("user@example.com")
        tracker.complete(task_id)
        # Manually set completed_at to 10 minutes ago
        from datetime import UTC, datetime, timedelta
        old_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        tracker._tasks[task_id].completed_at = old_time

        tracker._cleanup_stale()
        assert tracker.get(task_id) is None

    def test_multiple_tasks_independent(self):
        tracker = SyncProgressTracker()
        t1 = tracker.start("alice@example.com")
        t2 = tracker.start("bob@example.com")
        tracker.update_folder(t1, 1, "INBOX")
        tracker.update_folder(t2, 1, "Sent")

        p1 = tracker.get(t1)
        p2 = tracker.get(t2)
        assert p1["folder_name"] == "INBOX"
        assert p2["folder_name"] == "Sent"
        assert p1["task_id"] != p2["task_id"]


class TestSyncStatusEndpoint:
    """Test the GET /api/v1/email/sync/status endpoint."""

    def _client(self):
        from lighterbird.server.deps import reset_services
        reset_services()
        return TestClient(create_app())

    def test_sync_status_returns_startup_complete(self):
        """GET /sync/status returns startup_complete even with no accounts."""
        resp = self._client().get("/api/v1/email/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "startup_complete" in data
        assert "accounts" in data

    def test_sync_status_no_accounts(self):
        """With no accounts, startup is trivially complete."""
        resp = self._client().get("/api/v1/email/sync/status")
        data = resp.json()
        assert data["startup_complete"] is True
        assert data["accounts"] == []

    def test_sync_status_structure(self):
        """Response has the correct structure."""
        resp = self._client().get("/api/v1/email/sync/status")
        data = resp.json()
        assert isinstance(data["startup_complete"], bool)
        assert isinstance(data["accounts"], list)

    def test_sync_status_account_has_expected_fields(self):
        """Each account entry has expected fields."""
        # Register a test account via sync state manager
        from lighterbird.server.sync_state import get_sync_state_manager
        state_mgr = get_sync_state_manager()
        state_mgr.register_account("test@example.com")
        try:
            resp = self._client().get("/api/v1/email/sync/status")
            data = resp.json()
            assert len(data["accounts"]) >= 1
            acct = data["accounts"][0]
            assert "account_email" in acct
            assert "status" in acct
            assert "last_sync_at" in acct
            assert "last_error" in acct
            assert "idle_alive" in acct
            assert "idle_supported" in acct
            assert "last_idle_heartbeat" in acct
            assert "reconnects" in acct
        finally:
            state_mgr.remove_account("test@example.com")


class TestSyncProgressEndpoints:
    """Test the /api/v1/email/sync/start and progress endpoints."""

    def _client(self):
        from lighterbird.server.deps import reset_services
        reset_services()
        return TestClient(create_app())

    def test_sync_start_returns_task_id(self):
        """POST /api/v1/email/sync/start returns a task_id immediately."""
        resp = self._client().post("/api/v1/email/sync/start", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["account_email"] is None

    def test_sync_start_with_account(self):
        """POST with account_email returns it echoed back."""
        resp = self._client().post("/api/v1/email/sync/start", json={
            "account_email": "test@example.com",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["account_email"] == "test@example.com"

    def test_progress_unknown_task_returns_404(self):
        """GET /sync/progress/{unknown} returns 404."""
        resp = self._client().get("/api/v1/email/sync/progress/nonexistent")
        assert resp.status_code == 404

    def test_progress_after_start_is_running(self):
        """Progress of a just-started task should show 'running'."""
        start_resp = self._client().post("/api/v1/email/sync/start", json={})
        task_id = start_resp.json()["task_id"]

        import time
        time.sleep(0.5)  # Brief wait for thread to init

        prog_resp = self._client().get(f"/api/v1/email/sync/progress/{task_id}")
        assert prog_resp.status_code == 200
        data = prog_resp.json()
        assert data["task_id"] == task_id
        # Status may be "running" or "complete" depending on how fast
        # the background thread finishes (no accounts → instant complete)
        assert data["status"] in ("running", "complete")

    def test_sync_eventually_completes(self):
        """Sync task should eventually have status 'complete', even with errors."""
        start_resp = self._client().post("/api/v1/email/sync/start", json={})
        task_id = start_resp.json()["task_id"]

        # Wait for the background thread to finish (no accounts = fast)
        import time
        for _ in range(20):
            time.sleep(0.5)
            prog_resp = self._client().get(
                f"/api/v1/email/sync/progress/{task_id}"
            )
            if prog_resp.status_code == 200:
                data = prog_resp.json()
                if data["status"] in ("complete", "error"):
                    return  # Success! Task finished.
        assert False, "Sync task did not reach complete/error status within 10s"
