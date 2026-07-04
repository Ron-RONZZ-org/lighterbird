"""Tests for BackupScheduler — periodic auto-backup behavior.

Verifies that the scheduler:
1. Correctly identifies overdue strategies on startup
2. Correctly computes due/not-due strategies
3. Updates last_backup_at after running
4. Only runs enabled strategies
5. Runs strategies from config management (!backup config add/modify)
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from lighterbird.server.tasks import BackupScheduler
from lighterbird.core.backup import (
    load_config,
    save_config,
    list_strategies,
    add_strategy,
    BackupStrategy,
    _backup_dir,
)


class TestBackupScheduler:
    """Unit tests for BackupScheduler timing logic."""

    def test_strategy_due_on_startup(self, tmp_data_dir: Path, monkeypatch):
        """A strategy with interval > 0 and no last_backup_at is due immediately."""
        # Set up a strategy with 60 min interval, never backed up
        cfg = load_config()
        cfg["strategies"][0]["interval_minutes"] = 60
        cfg["strategies"][0]["last_backup_at"] = ""
        save_config(cfg)

        scheduler = BackupScheduler("test-scheduler")
        # _check_and_backup_if_due calls backup_all_strategies which needs DBs
        (tmp_data_dir / "email.db").write_text("data")

        # Run the check — should trigger because last_backup_at is empty
        scheduler._check_and_backup_if_due()

        # After running, last_backup_at should be set
        cfg = load_config()
        s = cfg["strategies"][0]
        assert s["last_backup_at"] != "", (
            "last_backup_at should be set after backup"
        )

    def test_strategy_due_after_interval(self, tmp_data_dir: Path, monkeypatch):
        """A strategy with a stale last_backup_at (past interval) is due."""
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        cfg = load_config()
        cfg["strategies"][0]["interval_minutes"] = 60
        cfg["strategies"][0]["last_backup_at"] = old_time
        save_config(cfg)

        (tmp_data_dir / "email.db").write_text("data")

        scheduler = BackupScheduler("test-scheduler")
        scheduler._check_and_backup_if_due()

        cfg = load_config()
        s = cfg["strategies"][0]
        assert s["last_backup_at"] != old_time, (
            "last_backup_at should be updated after backup"
        )

    def test_strategy_not_due_before_interval(self, tmp_data_dir: Path, monkeypatch):
        """A strategy with recent last_backup_at is NOT due."""
        recent = datetime.now(timezone.utc).isoformat()
        cfg = load_config()
        cfg["strategies"][0]["interval_minutes"] = 60
        cfg["strategies"][0]["last_backup_at"] = recent
        save_config(cfg)

        (tmp_data_dir / "email.db").write_text("data")

        scheduler = BackupScheduler("test-scheduler")
        # Track whether backup_all_strategies was called
        called = []

        original_backup = scheduler._check_and_backup_if_due
        # Just call the method — it should detect no due strategies
        scheduler._check_and_backup_if_due()

        # last_backup_at should remain the same (within a second tolerance)
        cfg = load_config()
        s = cfg["strategies"][0]
        # The timestamp might differ by a few microseconds but should be
        # the same second (the method didn't trigger a new backup)
        # Actually, since it should NOT have triggered, the timestamp is unchanged
        assert s["last_backup_at"] == recent, (
            "last_backup_at should NOT be updated when strategy is not due"
        )

    def test_disabled_strategy_not_run(self, tmp_data_dir: Path, monkeypatch):
        """A disabled strategy (enabled=False) is NOT run even if overdue."""
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        cfg = load_config()
        cfg["strategies"][0]["interval_minutes"] = 60
        cfg["strategies"][0]["last_backup_at"] = old_time
        cfg["strategies"][0]["enabled"] = False
        save_config(cfg)

        (tmp_data_dir / "email.db").write_text("data")

        scheduler = BackupScheduler("test-scheduler")
        scheduler._check_and_backup_if_due()

        # last_backup_at should remain the old value
        cfg = load_config()
        s = cfg["strategies"][0]
        assert s["last_backup_at"] == old_time, (
            "disabled strategy should NOT have its last_backup_at updated"
        )

    def test_on_demand_strategy_not_scheduled(self, tmp_data_dir: Path, monkeypatch):
        """A strategy with interval_minutes=0 is NOT auto-scheduled."""
        cfg = load_config()
        cfg["strategies"][0]["interval_minutes"] = 0
        cfg["strategies"][0]["last_backup_at"] = ""
        save_config(cfg)

        (tmp_data_dir / "email.db").write_text("data")

        scheduler = BackupScheduler("test-scheduler")
        scheduler._check_and_backup_if_due()

        # Should NOT have run (interval=0 means on-demand only)
        cfg = load_config()
        s = cfg["strategies"][0]
        assert s["last_backup_at"] == "", (
            "on-demand strategy should not be auto-backed up"
        )

    def test_scheduler_creates_backup_archive(self, tmp_data_dir: Path, monkeypatch):
        """_check_and_backup_if_due creates a .7z archive in .backups/."""
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        cfg = load_config()
        cfg["strategies"][0]["interval_minutes"] = 60
        cfg["strategies"][0]["last_backup_at"] = old_time
        save_config(cfg)

        (tmp_data_dir / "email.db").write_text("data")
        (tmp_data_dir / "todo.db").write_text("todo data")

        scheduler = BackupScheduler("test-scheduler")
        scheduler._check_and_backup_if_due()

        # Check that a .7z archive was created in .backups/
        backup_dir = _backup_dir()
        archives = list(backup_dir.glob("*.7z"))
        assert len(archives) >= 1, (
            f"No .7z archives found in {backup_dir}"
        )

    def test_scheduler_with_multiple_strategies(self, tmp_data_dir: Path, monkeypatch):
        """Multiple strategies should all get backed up independently."""
        # Set up default strategy
        cfg = load_config()
        cfg["strategies"][0]["interval_minutes"] = 60
        cfg["strategies"][0]["last_backup_at"] = (
            datetime.now(timezone.utc) - timedelta(hours=2)
        ).isoformat()
        save_config(cfg)

        # Add a second strategy via the proper API
        add_strategy(BackupStrategy(
            id="hourly",
            label="Hourly",
            interval_minutes=60,
            max_copies=5,
        ))

        (tmp_data_dir / "email.db").write_text("data")

        scheduler = BackupScheduler("test-scheduler")
        scheduler._check_and_backup_if_due()

        # Both strategies should have their last_backup_at updated
        cfg = load_config()
        strategies = {s["id"]: s for s in cfg["strategies"]}
        assert "default" in strategies
        assert strategies["default"]["last_backup_at"] != ""
        assert "hourly" in strategies
        assert strategies["hourly"]["last_backup_at"] != ""
