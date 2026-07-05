"""Tests for server/tasks.py — task orchestration, workers, backup scheduler.

Worker subclasses import service modules internally (to avoid circular deps),
so we mock those imports to test dispatch logic and error paths.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.core.worker import BackgroundWorker, Job, WorkerPool
from lighterbird.server.tasks import (
    BackupScheduler,
    CalDAVWorker,
    EmailSyncWorker,
    enqueue_caldav_push,
    enqueue_caldav_sync,
    enqueue_email_sync,
    enqueue_email_trash,
    get_worker_pool,
    init_workers,
    shutdown_workers,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level functions
# ═══════════════════════════════════════════════════════════════════════════════


class TestModuleFunctions:
    """Tests for top-level enqueue_* / init / shutdown functions."""

    def test_get_worker_pool(self):
        pool = get_worker_pool()
        assert isinstance(pool, WorkerPool)

    def test_enqueue_email_sync(self, monkeypatch):
        worker = MagicMock(spec=BackgroundWorker)
        pool = MagicMock(spec=WorkerPool)
        pool.get.return_value = worker
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)

        enqueue_email_sync("user@example.com")
        pool.get.assert_called_once_with("email")
        worker.enqueue.assert_called_once()
        job = worker.enqueue.call_args[0][0]
        assert job.domain == "email"
        assert job.operation == "sync"
        assert job.payload == {"account_email": "user@example.com"}

    def test_enqueue_email_sync_all(self, monkeypatch):
        worker = MagicMock(spec=BackgroundWorker)
        pool = MagicMock(spec=WorkerPool)
        pool.get.return_value = worker
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)

        enqueue_email_sync()  # no account = sync all
        job = worker.enqueue.call_args[0][0]
        assert job.payload == {}

    def test_enqueue_email_sync_worker_unavailable(self, monkeypatch):
        pool = MagicMock(spec=WorkerPool)
        pool.get.return_value = None
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)
        enqueue_email_sync("test@example.com")  # should not raise

    def test_enqueue_email_trash(self, monkeypatch):
        worker = MagicMock(spec=BackgroundWorker)
        pool = MagicMock(spec=WorkerPool)
        pool.get.return_value = worker
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)

        enqueue_email_trash("user@example.com")
        job = worker.enqueue.call_args[0][0]
        assert job.operation == "process_trash"

    def test_enqueue_email_trash_worker_unavailable(self, monkeypatch):
        pool = MagicMock(spec=WorkerPool)
        pool.get.return_value = None
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)
        enqueue_email_trash()  # should not raise

    def test_enqueue_caldav_push(self, monkeypatch):
        worker = MagicMock(spec=BackgroundWorker)
        pool = MagicMock(spec=WorkerPool)
        pool.get.return_value = worker
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)

        enqueue_caldav_push("cal-1", "evt-1", operation="push")
        job = worker.enqueue.call_args[0][0]
        assert job.domain == "caldav"
        assert job.operation == "push"
        assert job.payload == {"calendar_uuid": "cal-1", "event_uuid": "evt-1"}

    def test_enqueue_caldav_push_delete(self, monkeypatch):
        worker = MagicMock(spec=BackgroundWorker)
        pool = MagicMock(spec=WorkerPool)
        pool.get.return_value = worker
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)

        enqueue_caldav_push("cal-1", "evt-1", operation="delete")
        job = worker.enqueue.call_args[0][0]
        assert job.operation == "delete"

    def test_enqueue_caldav_push_worker_unavailable(self, monkeypatch):
        pool = MagicMock(spec=WorkerPool)
        pool.get.return_value = None
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)
        enqueue_caldav_push("cal-1", "evt-1")  # should not raise

    def test_enqueue_caldav_sync(self, monkeypatch):
        worker = MagicMock(spec=BackgroundWorker)
        pool = MagicMock(spec=WorkerPool)
        pool.get.return_value = worker
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)

        enqueue_caldav_sync("cal-1")
        job = worker.enqueue.call_args[0][0]
        assert job.operation == "pull"

    def test_enqueue_caldav_sync_worker_unavailable(self, monkeypatch):
        pool = MagicMock(spec=WorkerPool)
        pool.get.return_value = None
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)
        enqueue_caldav_sync("cal-1")  # should not raise

    def test_shutdown_workers(self, monkeypatch):
        pool = MagicMock(spec=WorkerPool)
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)
        shutdown_workers(timeout=3.0)
        pool.stop_all.assert_called_once_with(timeout=3.0)


# ═══════════════════════════════════════════════════════════════════════════════
# EmailSyncWorker
# ═══════════════════════════════════════════════════════════════════════════════


class TestEmailSyncWorker:
    def test_execute_job_dispatch_sync(self):
        worker = EmailSyncWorker("test-email")
        with patch.object(worker, "_do_sync") as mock_sync:
            worker.execute_job(Job("email", "sync", {"k": "v"}))
            mock_sync.assert_called_once_with({"k": "v"})

    def test_execute_job_dispatch_trash(self):
        worker = EmailSyncWorker("test-email")
        with patch.object(worker, "_do_process_trash") as mock_trash:
            worker.execute_job(Job("email", "process_trash", {"k": "v"}))
            mock_trash.assert_called_once_with({"k": "v"})

    def test_execute_job_unknown_operation(self):
        """Unknown operation logs but does not raise."""
        worker = EmailSyncWorker("test-email")
        worker.execute_job(Job("email", "unknown_op"))  # should not raise

    def test_execute_job_wrong_domain(self):
        """Non-email jobs are ignored."""
        worker = EmailSyncWorker("test-email")
        worker.execute_job(Job("caldav", "sync"))  # should not raise

    @patch("lighterbird.email.service.EmailService")
    def test_do_sync_single_account(self, mock_svc_cls):
        worker = EmailSyncWorker("test-email")
        svc = MagicMock()
        svc.process_sync_backlog.return_value = 0
        svc.process_send_queue.return_value = {}
        mock_svc_cls.return_value = svc

        worker._do_sync({"account_email": "user@example.com"})
        svc.sync_account.assert_called_once_with("user@example.com")
        svc.process_sync_backlog.assert_called_once()
        svc.process_send_queue.assert_called_once()

    @patch("lighterbird.email.service.EmailService")
    def test_do_sync_all_accounts(self, mock_svc_cls):
        worker = EmailSyncWorker("test-email")
        svc = MagicMock()
        svc.list_accounts.return_value = [
            {"email": "a@b.com"},
            {"email": "c@d.com"},
        ]
        svc.process_sync_backlog.return_value = 3
        svc.process_send_queue.return_value = {"sent": 1, "retrying": 0}
        mock_svc_cls.return_value = svc

        worker._do_sync({})
        assert svc.sync_account.call_count == 2
        svc.sync_account.assert_any_call("a@b.com")
        svc.sync_account.assert_any_call("c@d.com")

    @patch("lighterbird.email.service.EmailService")
    def test_do_process_trash(self, mock_svc_cls):
        worker = EmailSyncWorker("test-email")
        svc = MagicMock()
        mock_svc_cls.return_value = svc

        worker._do_process_trash({"account_email": "user@example.com"})
        svc.msg_ops.process_trash_backlog.assert_called_once_with(
            account_email="user@example.com"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CalDAVWorker
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalDAVWorker:
    def test_execute_job_dispatch_pull(self):
        worker = CalDAVWorker("test-caldav")
        with patch.object(worker, "_do_pull") as mock_pull:
            worker.execute_job(Job("caldav", "pull", {"k": "v"}))
            mock_pull.assert_called_once_with({"k": "v"})

    def test_execute_job_dispatch_push(self):
        worker = CalDAVWorker("test-caldav")
        with patch.object(worker, "_do_push") as mock_push:
            worker.execute_job(Job("caldav", "push", {"k": "v"}))
            mock_push.assert_called_once_with({"k": "v"})

    def test_execute_job_dispatch_delete(self):
        worker = CalDAVWorker("test-caldav")
        with patch.object(worker, "_do_delete") as mock_delete:
            worker.execute_job(Job("caldav", "delete", {"k": "v"}))
            mock_delete.assert_called_once_with({"k": "v"})

    def test_execute_job_unknown_operation(self):
        worker = CalDAVWorker("test-caldav")
        worker.execute_job(Job("caldav", "unknown"))  # should not raise

    def test_execute_job_wrong_domain(self):
        worker = CalDAVWorker("test-caldav")
        worker.execute_job(Job("email", "push"))  # should not raise

    @patch("lighterbird.calendar.service.CalendarService")
    def test_do_pull(self, mock_cal_svc_cls):
        worker = CalDAVWorker("test-caldav")
        svc = MagicMock()
        mock_cal_svc_cls.return_value = svc

        worker._do_pull({"calendar_uuid": "cal-1"})
        svc.sync_calendar.assert_called_once_with("cal-1")
        svc.events.process_sync_queue.assert_called_once()

    @patch("lighterbird.calendar.service.CalendarService")
    def test_do_pull_empty_uuid(self, mock_cal_svc_cls):
        worker = CalDAVWorker("test-caldav")
        worker._do_pull({"calendar_uuid": ""})  # should not raise

    @patch("lighterbird.calendar.caldav.push_event")
    @patch("lighterbird.calendar.ics.events_to_ics")
    @patch("lighterbird.calendar.keyring.get_password")
    @patch("lighterbird.calendar.service.CalendarService")
    def test_do_push(
        self, mock_cal_svc_cls, mock_get_pw, mock_ics, mock_push
    ):
        worker = CalDAVWorker("test-caldav")
        svc = MagicMock()
        svc.calendars.get.return_value = {
            "url": "https://caldav.example.com/cal",
            "username": "user",
        }
        svc.events.get.return_value = {"uuid": "evt-1", "remote_href": "/cal/evt.ics"}
        mock_cal_svc_cls.return_value = svc
        mock_get_pw.return_value = "secret"
        mock_ics.return_value = "BEGIN:VCALENDAR..."

        worker._do_push({"calendar_uuid": "cal-1", "event_uuid": "evt-1"})
        mock_push.assert_called_once()
        args = mock_push.call_args.kwargs
        assert args["url"] == "https://caldav.example.com/cal"
        assert args["password"] == "secret"
        assert args["remote_href"] == "/cal/evt.ics"

    @patch("lighterbird.calendar.service.CalendarService")
    def test_do_push_missing_calendar(self, mock_cal_svc_cls):
        worker = CalDAVWorker("test-caldav")
        svc = MagicMock()
        svc.calendars.get.return_value = None
        mock_cal_svc_cls.return_value = svc

        worker._do_push({"calendar_uuid": "cal-1", "event_uuid": "evt-1"})
        svc.events.get.assert_not_called()  # exits early

    @patch("lighterbird.calendar.service.CalendarService")
    def test_do_push_missing_event(self, mock_cal_svc_cls):
        worker = CalDAVWorker("test-caldav")
        svc = MagicMock()
        svc.calendars.get.return_value = {"url": "https://x.com/cal", "username": "u"}
        svc.events.get.return_value = None
        mock_cal_svc_cls.return_value = svc

        worker._do_push({"calendar_uuid": "cal-1", "event_uuid": "evt-1"})

    @patch("lighterbird.calendar.keyring.get_password")
    @patch("lighterbird.calendar.service.CalendarService")
    def test_do_push_missing_password(self, mock_cal_svc_cls, mock_get_pw):
        worker = CalDAVWorker("test-caldav")
        svc = MagicMock()
        svc.calendars.get.return_value = {"url": "https://x.com/cal", "username": "u"}
        svc.events.get.return_value = {"uuid": "evt-1"}
        mock_cal_svc_cls.return_value = svc
        mock_get_pw.return_value = None  # no password

        worker._do_push({"calendar_uuid": "cal-1", "event_uuid": "evt-1"})

    @patch("lighterbird.calendar.caldav.delete_event")
    @patch("lighterbird.calendar.keyring.get_password")
    @patch("lighterbird.calendar.service.CalendarService")
    def test_do_delete(
        self, mock_cal_svc_cls, mock_get_pw, mock_delete
    ):
        worker = CalDAVWorker("test-caldav")
        svc = MagicMock()
        svc.calendars.get.return_value = {
            "url": "https://caldav.example.com/cal",
            "username": "user",
        }
        svc.events.get.return_value = {"uuid": "evt-1", "remote_href": "/cal/evt.ics"}
        mock_cal_svc_cls.return_value = svc
        mock_get_pw.return_value = "secret"

        worker._do_delete({"calendar_uuid": "cal-1", "event_uuid": "evt-1"})
        mock_delete.assert_called_once()
        args = mock_delete.call_args.kwargs
        assert args["url"] == "https://caldav.example.com/cal"

    @patch("lighterbird.calendar.service.CalendarService")
    def test_do_delete_missing_params(self, mock_cal_svc_cls):
        worker = CalDAVWorker("test-caldav")
        worker._do_delete({"calendar_uuid": ""})  # should not raise


# ═══════════════════════════════════════════════════════════════════════════════
# BackupScheduler
# ═══════════════════════════════════════════════════════════════════════════════


class TestBackupScheduler:
    def test_execute_job_dispatch_scheduled(self):
        worker = BackupScheduler("test-backup")
        with patch.object(worker, "_check_and_backup_if_due") as mock_check:
            worker.execute_job(Job("backup", "scheduled_backup"))
            mock_check.assert_called_once()

    def test_execute_job_unknown_operation(self):
        worker = BackupScheduler("test-backup")
        worker.execute_job(Job("backup", "unknown"))  # should not raise

    def test_execute_job_wrong_domain(self):
        worker = BackupScheduler("test-backup")
        worker.execute_job(Job("email", "sync"))  # should not raise

    @patch("lighterbird.core.backup.load_config")
    @patch("lighterbird.core.backup.save_config")
    @patch("lighterbird.core.backup.backup_all_strategies")
    def test_check_and_backup_if_due_empty_strategies(
        self, mock_backup, mock_save, mock_load
    ):
        """No strategies → nothing to do."""
        mock_load.return_value = {"strategies": []}
        worker = BackupScheduler("test-backup")
        worker._check_and_backup_if_due()
        mock_backup.assert_not_called()

    @patch("lighterbird.core.backup.load_config")
    @patch("lighterbird.core.backup.save_config")
    @patch("lighterbird.core.backup.backup_all_strategies")
    def test_check_and_backup_if_due_disabled_strategy(
        self, mock_backup, mock_save, mock_load
    ):
        """Disabled strategy is skipped."""
        mock_load.return_value = {
            "strategies": [
                {"id": "daily", "interval_minutes": 1440, "enabled": False},
            ]
        }
        worker = BackupScheduler("test-backup")
        worker._check_and_backup_if_due()
        mock_backup.assert_not_called()

    @patch("lighterbird.core.backup.load_config")
    @patch("lighterbird.core.backup.save_config")
    @patch("lighterbird.core.backup.backup_all_strategies")
    def test_check_and_backup_if_due_zero_interval(
        self, mock_backup, mock_save, mock_load
    ):
        """Strategy with zero/no interval is skipped."""
        mock_load.return_value = {
            "strategies": [
                {"id": "manual", "interval_minutes": 0, "enabled": True},
            ]
        }
        worker = BackupScheduler("test-backup")
        worker._check_and_backup_if_due()
        mock_backup.assert_not_called()

    @patch("lighterbird.core.backup.load_config")
    @patch("lighterbird.core.backup.save_config")
    @patch("lighterbird.core.backup.backup_all_strategies")
    def test_check_and_backup_if_due_overdue(
        self, mock_backup, mock_save, mock_load
    ):
        """Strategy past its interval triggers backup."""
        from datetime import UTC, datetime, timedelta

        hours_ago = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        mock_load.return_value = {
            "strategies": [
                {
                    "id": "daily",
                    "interval_minutes": 1440,
                    "enabled": True,
                    "last_backup_at": hours_ago,
                },
            ]
        }
        worker = BackupScheduler("test-backup")
        worker._check_and_backup_if_due()
        mock_backup.assert_called_once()

    @patch("lighterbird.core.backup.load_config")
    @patch("lighterbird.core.backup.save_config")
    @patch("lighterbird.core.backup.backup_all_strategies")
    def test_check_and_backup_updates_timestamp(
        self, mock_backup, mock_save, mock_load
    ):
        """After backup, last_backup_at is updated."""
        from datetime import UTC, datetime, timedelta

        hours_ago = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        cfg = {
            "strategies": [
                {
                    "id": "daily",
                    "interval_minutes": 1440,
                    "enabled": True,
                    "last_backup_at": hours_ago,
                },
            ]
        }
        mock_load.return_value = cfg
        worker = BackupScheduler("test-backup")
        worker._check_and_backup_if_due()
        mock_save.assert_called_once()
        saved_cfg = mock_save.call_args[0][0]
        assert saved_cfg["strategies"][0]["last_backup_at"] is not None
        assert saved_cfg["strategies"][0]["last_backup_at"] != hours_ago

    @patch("lighterbird.core.backup.load_config")
    @patch("lighterbird.core.backup.save_config")
    @patch("lighterbird.core.backup.backup_all_strategies")
    def test_check_and_backup_if_due_not_yet_due(
        self, mock_backup, mock_save, mock_load
    ):
        """Strategy within its interval does not trigger backup."""
        from datetime import UTC, datetime

        recently = datetime.now(UTC).isoformat()
        mock_load.return_value = {
            "strategies": [
                {
                    "id": "daily",
                    "interval_minutes": 1440,
                    "enabled": True,
                    "last_backup_at": recently,
                },
            ]
        }
        worker = BackupScheduler("test-backup")
        worker._check_and_backup_if_due()
        mock_backup.assert_not_called()

    @patch("lighterbird.core.backup.load_config")
    @patch("lighterbird.core.backup.save_config")
    @patch("lighterbird.core.backup.backup_all_strategies")
    def test_check_and_backup_invalid_last_backup_at(
        self, mock_backup, mock_save, mock_load
    ):
        """Corrupted last_backup_at is treated as overdue."""
        mock_load.return_value = {
            "strategies": [
                {
                    "id": "daily",
                    "interval_minutes": 1440,
                    "enabled": True,
                    "last_backup_at": "not-a-date",
                },
            ]
        }
        worker = BackupScheduler("test-backup")
        worker._check_and_backup_if_due()
        mock_backup.assert_called_once()

    @patch("lighterbird.core.backup.load_config")
    def test_check_and_backup_load_error(self, mock_load):
        """Exception during config load is caught and logged."""
        mock_load.side_effect = RuntimeError("Config corrupted")
        worker = BackupScheduler("test-backup")
        worker._check_and_backup_if_due()  # should not raise

    def test_start_is_idempotent(self):
        """Starting an already-running scheduler does nothing."""
        worker = BackupScheduler("test-backup")
        worker._thread = MagicMock()
        worker._thread.is_alive.return_value = True
        worker.start()  # should not create a new thread

    def test_init_workers(self, monkeypatch):
        """init_workers adds and starts all three workers."""
        pool = MagicMock(spec=WorkerPool)
        monkeypatch.setattr("lighterbird.server.tasks._pool", pool)

        result = init_workers()
        # Should have added email, caldav, and backup workers
        assert pool.add.call_count == 3
        pool.start_all.assert_called_once()
        assert result is pool
