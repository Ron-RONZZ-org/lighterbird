"""Task orchestration — wires domain services to background workers.

Provides ``enqueue_*()`` functions called by route handlers and service
facades to offload work (sync, push) to background threads.

Also manages the startup sync and IMAP IDLE lifecycle.
"""

from __future__ import annotations

import logging
import threading
import time as _time
from datetime import UTC, datetime

from lighterbird.core.worker import BackgroundWorker, Job, WorkerPool

logger = logging.getLogger(__name__)

# ── Global worker pool (initialized by FastAPI lifespan) ──────────────────

_pool = WorkerPool()

# ── IDLE debounce timer (kept here so callbacks can reach it) ─────────────

# Per-account debounce timers: account_email -> threading.Timer
_idle_debounce: dict[str, threading.Timer | None] = {}
_idle_debounce_lock = threading.Lock()


def _do_idle_sync(account_email: str) -> None:
    """Called by the IDLE debounce timer — enqueues an incremental sync."""
    enqueue_email_sync(account_email)


def _make_idle_callback(account_email: str):
    """Return a debounced callback for IMAPIdleThread notifications.

    If multiple EXISTS/FLAGS notifications arrive within 2 seconds,
    only one sync job is enqueued.
    """
    def on_notification(acct_email: str, folder: str, event_type: str) -> None:
        logger.debug("[idle] Notification on %s/%s: %s", acct_email, folder, event_type)
        # Track notification in sync state
        try:
            from lighterbird.server.sync_state import get_sync_state_manager
            state_mgr = get_sync_state_manager()
            state_mgr.set_status(acct_email, "idle")
        except Exception:
            pass

        # Debounce: cancel previous timer, schedule new one in 2s
        with _idle_debounce_lock:
            old = _idle_debounce.get(acct_email)
            if old is not None:
                old.cancel()
            timer = threading.Timer(2.0, _do_idle_sync, args=[acct_email])
            timer.daemon = True
            timer.start()
            _idle_debounce[acct_email] = timer

    return on_notification


def _start_idle_for_account(account_email: str) -> bool:
    """Start an IDLE thread for a single account.

    Returns True if started, False if already running or config missing.
    """
    from lighterbird.email.imap.idle import get_imap_idle_manager
    from lighterbird.server.deps import get_email_service

    svc = get_email_service()
    full_acct = svc.accounts.get_account_with_password(account_email)
    if not full_acct or not full_acct.get("password"):
        logger.warning("[idle] No password for %s, skipping IDLE", account_email)
        return False

    idle_mgr = get_imap_idle_manager()
    return idle_mgr.start_for_account(
        account_email=account_email,
        host=full_acct["imap_server"],
        port=full_acct["imap_port"],
        use_ssl=full_acct.get("imap_use_ssl", 1) == 1,
        username=full_acct.get("imap_username", "") or account_email,
        password=full_acct["password"],
        on_notification=_make_idle_callback(account_email),
    )


def _start_idle_for_all_accounts() -> None:
    """Start IDLE threads for all configured accounts."""
    from lighterbird.server.deps import get_email_service
    from lighterbird.server.sync_state import get_sync_state_manager

    svc = get_email_service()
    state_mgr = get_sync_state_manager()

    for acct in svc.list_accounts():
        email = acct["email"]
        started = _start_idle_for_account(email)
        if started:
            state_mgr.set_status(email, "idle")
            state_mgr.set_idle_status(email, alive=True, supported=True)
            logger.info("[idle] IDLE thread started for %s", email)
        else:
            state_mgr.set_status(email, "disabled")
            state_mgr.set_idle_status(email, alive=False, supported=False)
            logger.info("[idle] IDLE not started for %s (no password or already running)", email)


def start_idle_for_new_account(account_email: str) -> None:
    """Start an IDLE thread for a newly created account."""
    from lighterbird.server.sync_state import get_sync_state_manager

    state_mgr = get_sync_state_manager()
    state_mgr.register_account(account_email)

    started = _start_idle_for_account(account_email)
    if started:
        state_mgr.set_status(account_email, "idle")
        state_mgr.set_idle_status(account_email, alive=True, supported=True)
    else:
        state_mgr.set_status(account_email, "disabled")


def stop_idle_for_account(account_email: str) -> None:
    """Stop the IDLE thread for a deleted or updated account."""
    from lighterbird.email.imap.idle import get_imap_idle_manager
    from lighterbird.server.sync_state import get_sync_state_manager

    idle_mgr = get_imap_idle_manager()
    idle_mgr.stop_for_account(account_email)

    state_mgr = get_sync_state_manager()
    state_mgr.remove_account(account_email)

    # Clean up any pending debounce timer
    with _idle_debounce_lock:
        old = _idle_debounce.pop(account_email, None)
        if old is not None:
            old.cancel()


def stop_all_idle() -> None:
    """Stop all IDLE threads and clean up."""
    from lighterbird.email.imap.idle import get_imap_idle_manager

    with _idle_debounce_lock:
        for timer in _idle_debounce.values():
            if timer is not None:
                timer.cancel()
        _idle_debounce.clear()

    idle_mgr = get_imap_idle_manager()
    idle_mgr.stop_all()


def init_workers() -> WorkerPool:
    """Create, register, and start all background workers.

    Called from ``server/app.py`` lifespan startup.

    Returns:
        The configured :class:`WorkerPool` instance.
    """
    _pool.add("email", EmailSyncWorker("email-sync"))
    _pool.add("caldav", CalDAVWorker("caldav-sync"))
    _pool.add("backup", BackupScheduler("backup-scheduler"))
    _pool.start_all()
    logger.info("[tasks] All workers started")
    return _pool


def shutdown_workers(timeout: float = 5.0) -> None:
    """Stop all background workers.

    Called from ``server/app.py`` lifespan shutdown.

    Args:
        timeout: Max seconds to wait for active jobs to finish.
    """
    # Stop IDLE threads first
    stop_all_idle()

    _pool.stop_all(timeout=timeout)
    logger.info("[tasks] All workers stopped")


def get_worker_pool() -> WorkerPool:
    """Return the global worker pool (for health checks, status)."""
    return _pool


# ── Email sync ────────────────────────────────────────────────────────────


def enqueue_email_sync(account_email: str | None = None) -> None:
    """Enqueue an email sync job.

    Args:
        account_email: Sync a specific account (by email), or ``None`` for all.
    """
    worker = _pool.get("email")
    if worker is None:
        logger.warning("[tasks] Email worker not available")
        return
    worker.enqueue(
        Job(
            domain="email",
            operation="sync",
            payload={"account_email": account_email} if account_email else {},
        )
    )


def enqueue_email_send() -> None:
    """Enqueue a background send-queue processing job.

    Triggers :meth:`EmailService.process_send_queue` on the email
    worker, delivering any queued outbound messages via SMTP.
    """
    worker = _pool.get("email")
    if worker is None:
        logger.warning("[tasks] Email worker not available")
        return
    worker.enqueue(
        Job(
            domain="email",
            operation="send",
            payload={},
        )
    )


def enqueue_email_trash(account_email: str | None = None) -> None:
    """Enqueue a background trash queue drain job.

    Processes pending IMAP trash operations from the backlog.
    Args:
        account_email: If None, processes trash for all accounts.
    """
    worker = _pool.get("email")
    if worker is None:
        logger.warning("[tasks] Email worker not available")
        return
    worker.enqueue(
        Job(
            domain="email",
            operation="process_trash",
            payload={"account_email": account_email} if account_email else {},
        )
    )


# ── CalDAV sync / push ───────────────────────────────────────────────────


def enqueue_caldav_push(
    calendar_uuid: str,
    event_uuid: str,
    operation: str = "push",
) -> None:
    """Enqueue a CalDAV push or delete job.

    Args:
        calendar_uuid: The calendar to push to.
        event_uuid: The event to push or delete.
        operation: ``"push"`` (create/update) or ``"delete"``.
    """
    worker = _pool.get("caldav")
    if worker is None:
        logger.warning("[tasks] CalDAV worker not available")
        return
    worker.enqueue(
        Job(
            domain="caldav",
            operation="push" if operation == "push" else "delete",
            payload={
                "calendar_uuid": calendar_uuid,
                "event_uuid": event_uuid,
            },
        )
    )


def enqueue_caldav_sync(calendar_uuid: str) -> None:
    """Enqueue a CalDAV pull sync job.

    Args:
        calendar_uuid: The calendar to pull events from.
    """
    worker = _pool.get("caldav")
    if worker is None:
        logger.warning("[tasks] CalDAV worker not available")
        return
    worker.enqueue(
        Job(
            domain="caldav",
            operation="pull",
            payload={"calendar_uuid": calendar_uuid},
        )
    )


# ── Worker process functions (called by BackgroundWorker.execute_job) ─────


class EmailSyncWorker(BackgroundWorker):
    """BackgroundWorker subclass that handles email sync and trash jobs.

    On startup, enqueues an initial full sync for all accounts, then
    transitions to IDLE mode (or periodic polling for non-IDLE servers).
    """

    _POLL_INTERVAL = 300  # 5 minutes between polling cycles for non-IDLE accounts

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._poll_timer: threading.Timer | None = None

    def start(self) -> None:
        """Start the worker thread and enqueue startup sync."""
        super().start()
        # Enqueue startup sync — this will trigger after the worker
        # thread has started consuming jobs.
        self.enqueue(
            Job(domain="email", operation="startup-sync", payload={})
        )
        logger.info("[tasks] Startup sync enqueued")
        # Start periodic polling for non-IDLE accounts
        self._schedule_poll()

    def stop(self, timeout: float = 3.0) -> None:
        """Stop the worker and cancel the poll timer."""
        if self._poll_timer is not None:
            self._poll_timer.cancel()
            self._poll_timer = None
        super().stop(timeout=timeout)

    def _schedule_poll(self) -> None:
        """Schedule a periodic poll for accounts without IDLE."""
        if self._poll_timer is not None:
            self._poll_timer.cancel()

        timer = threading.Timer(self._POLL_INTERVAL, self._do_poll_check)
        timer.daemon = True
        timer.start()
        self._poll_timer = timer

    def _do_poll_check(self) -> None:
        """Check for accounts without IDLE and enqueue sync for them."""
        try:
            from lighterbird.server.sync_state import get_sync_state_manager

            state_mgr = get_sync_state_manager()
            needs_poll = False
            for acct_state in state_mgr.all_states():
                # Enqueue sync for accounts without IDLE or with disconnected IDLE
                if not acct_state.get("idle_alive", False):
                    email = acct_state.get("account_email", "")
                    if email:
                        needs_poll = True
                        self.enqueue(
                            Job(
                                domain="email",
                                operation="sync",
                                payload={"account_email": email},
                            )
                        )
            if needs_poll:
                logger.debug("[tasks] Poll check: enqueued sync for non-IDLE accounts")
        except Exception as exc:
            logger.warning("[tasks] Poll check failed: %s", exc)
        finally:
            # Reschedule for next cycle
            self._schedule_poll()

    def execute_job(self, job: Job) -> None:
        if job.domain != "email":
            logger.debug("Ignoring non-email job: %s/%s", job.domain, job.operation)
            return

        if job.operation == "startup-sync":
            self._do_startup_sync(job.payload)
        elif job.operation == "sync":
            self._do_sync(job.payload)
        elif job.operation == "send":
            self._do_send(job.payload)
        elif job.operation == "process_trash":
            self._do_process_trash(job.payload)
        else:
            logger.warning("Unknown email operation: %s", job.operation)

    @staticmethod
    def _do_startup_sync(payload: dict) -> None:
        """Run the initial full sync, then start IDLE threads."""
        from lighterbird.server.deps import get_email_service
        from lighterbird.server.sync_state import get_sync_state_manager

        svc = get_email_service()
        state_mgr = get_sync_state_manager()
        accounts = svc.list_accounts()

        if not accounts:
            logger.info("[tasks] No email accounts configured, skipping startup sync")
            return

        # Register all accounts in sync state
        for acct in accounts:
            email = acct["email"]
            state_mgr.register_account(email)

        # Sync all accounts
        logger.info("[tasks] Starting initial full sync for %d account(s)", len(accounts))
        for acct in accounts:
            email = acct["email"]
            try:
                state_mgr.set_status(email, "startup-syncing")
                sr = svc.sync_account(email)
                logger.info("[tasks] Startup sync for %s: %d total, %d new",
                            email, sr.total, sr.new)

                # Pull server-side flag changes via CONDSTORE (if supported)
                pull_result = svc.msg_ops.flag_sync.pull_changes(email)
                if pull_result:
                    logger.info(
                        "[tasks] Pulled %s flag changes for %s",
                        sum(pull_result.values()), email,
                    )

                state_mgr.set_last_sync(email)
            except Exception as e:
                logger.error("[tasks] Startup sync failed for %s: %s", email, e)
                state_mgr.set_status(email, "error", error=str(e))

        # Drain pending flag sync backlog
        try:
            backlog = svc.process_sync_backlog()
            if backlog:
                logger.info("[tasks] Drained %d pending flag syncs from backlog", backlog)
        except Exception as e:
            logger.warning("[tasks] Backlog drain after startup failed: %s", e)

        # Start IDLE threads after all accounts are synced
        _start_idle_for_all_accounts()
        logger.info("[tasks] Startup sync complete, IDLE threads started")

    @staticmethod
    def _do_sync(payload: dict) -> None:
        """Run email sync — imports here to avoid circular deps."""
        from lighterbird.server.deps import get_email_service

        svc = get_email_service()
        account_email = payload.get("account_email")
        if account_email:
            svc.sync_account(account_email)
            # Pull server-side flag changes via CONDSTORE (if supported)
            pull_result = svc.msg_ops.flag_sync.pull_changes(account_email)
            if pull_result:
                logger.info(
                    "[tasks] Pulled %s flag changes for %s",
                    sum(pull_result.values()), account_email,
                )
        else:
            for account in svc.list_accounts():
                acct_email = account["email"]
                svc.sync_account(acct_email)
                pull_result = svc.msg_ops.flag_sync.pull_changes(acct_email)
                if pull_result:
                    logger.info(
                        "[tasks] Pulled %s flag changes for %s",
                        sum(pull_result.values()), acct_email,
                    )
        # Always drain the flag sync backlog after any sync pass,
        # ensuring \\Seen and \\Deleted flags queued by mark_read()
        # and trash_message() are pushed to the IMAP server even if
        # sync_account returned early (e.g., no password).
        backlog = svc.process_sync_backlog()
        if backlog:
            logger.info(
                "[tasks] Drained %d pending flag syncs from backlog",
                backlog,
            )
        # Drain the send queue (outbound emails that failed on first attempt)
        send_result = svc.process_send_queue()
        if send_result.get("sent") or send_result.get("retrying"):
            logger.info(
                "[tasks] Send queue: %d sent, %d retrying, %d failed",
                send_result.get("sent", 0),
                send_result.get("retrying", 0),
                send_result.get("failed", 0),
            )

    @staticmethod
    def _do_send(payload: dict) -> None:
        """Process the send queue — delivers queued outbound messages via SMTP.

        Runs :meth:`EmailService.process_send_queue` to flush any pending
        outbox entries.  Messages move from ``"Outbox"`` to ``"Sent"`` on
        success, or stay in the queue with exponential backoff on failure.
        """
        from lighterbird.server.deps import get_email_service

        svc = get_email_service()
        result = svc.process_send_queue()
        if result.get("sent") or result.get("retrying") or result.get("failed"):
            logger.info(
                "[tasks] Send queue: %d sent, %d retrying, %d failed",
                result.get("sent", 0),
                result.get("retrying", 0),
                result.get("failed", 0),
            )

    @staticmethod
    def _do_process_trash(payload: dict) -> None:
        """Process pending IMAP trash operations in the background.

        Opens one IMAP connection per account and moves all queued
        messages to the server-side Trash folder.

        Args:
            payload: May contain ``"account_email"`` to process a single
                     account, or ``None`` / missing to process all accounts.
        """
        from lighterbird.server.deps import get_email_service

        svc = get_email_service()
        account_email = payload.get("account_email")
        svc.msg_ops.process_trash_backlog(account_email=account_email)


class CalDAVWorker(BackgroundWorker):
    """BackgroundWorker subclass that handles CalDAV jobs."""

    def execute_job(self, job: Job) -> None:
        if job.domain != "caldav":
            logger.debug("Ignoring non-caldav job: %s/%s", job.domain, job.operation)
            return

        if job.operation == "pull":
            self._do_pull(job.payload)
        elif job.operation == "push":
            self._do_push(job.payload)
        elif job.operation == "delete":
            self._do_delete(job.payload)
        else:
            logger.warning("Unknown caldav operation: %s", job.operation)

    @staticmethod
    def _do_pull(payload: dict) -> None:
        """Pull events from a remote calendar."""
        from lighterbird.calendar.service import CalendarService

        cal_uuid = payload.get("calendar_uuid", "")
        if cal_uuid:
            svc = CalendarService()
            svc.sync_calendar(cal_uuid)
            # Also process any pending push/delete jobs
            svc.events.process_sync_queue()

    @staticmethod
    def _do_push(payload: dict) -> None:
        """Push an event to a remote calendar."""
        from lighterbird.calendar.caldav import push_event
        from lighterbird.calendar.ics import events_to_ics
        from lighterbird.calendar.keyring import get_password
        from lighterbird.calendar.service import CalendarService

        cal_uuid = payload.get("calendar_uuid", "")
        event_uuid = payload.get("event_uuid", "")
        if not cal_uuid or not event_uuid:
            logger.warning("CalDAV push missing calendar_uuid or event_uuid")
            return

        svc = CalendarService()
        cal = svc.calendars.get(cal_uuid)
        if not cal:
            logger.warning("Calendar not found: %s", cal_uuid[:8])
            return

        event = svc.events.get(event_uuid)
        if not event:
            logger.warning("Event not found: %s", event_uuid[:8])
            return

        password = get_password(cal_uuid)
        if not password:
            logger.warning("No password in keyring for calendar %s", cal_uuid[:8])
            return

        ics_data = events_to_ics([event])
        remote_href = event.get("remote_href") or None
        push_event(
            url=cal["url"],
            username=cal["username"],
            password=password,
            ics_payload=ics_data,
            event_uuid=event_uuid,
            remote_href=remote_href,
        )
        logger.info(
            "Pushed event %s to calendar %s", event_uuid[:8], cal_uuid[:8]
        )

    @staticmethod
    def _do_delete(payload: dict) -> None:
        """Delete an event from a remote calendar."""
        from lighterbird.calendar.caldav import delete_event
        from lighterbird.calendar.keyring import get_password
        from lighterbird.calendar.service import CalendarService

        cal_uuid = payload.get("calendar_uuid", "")
        event_uuid = payload.get("event_uuid", "")
        if not cal_uuid or not event_uuid:
            return

        svc = CalendarService()
        cal = svc.calendars.get(cal_uuid)
        if not cal:
            return

        event = svc.events.get(event_uuid)
        if not event:
            return

        password = get_password(cal_uuid)
        remote_href = event.get("remote_href")

        delete_event(
            url=cal["url"],
            username=cal["username"],
            password=password or "",
            event_uuid=event_uuid,
            remote_href=remote_href,
        )
        logger.info(
            "Deleted event %s from calendar %s", event_uuid[:8], cal_uuid[:8]
        )


# ── Backup scheduler ─────────────────────────────────────────────────────


class BackupScheduler(BackgroundWorker):
    """Background worker that runs scheduled backups per strategy.

    On startup, checks if any strategy with a positive interval is overdue
    (last_backup_at + interval > now) and runs it immediately.  Then
    checks every 60 seconds and runs any strategy that is due.
    """

    CHECK_INTERVAL = 60  # seconds between scheduler checks

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._last_checked: float = 0.0

    def execute_job(self, job: Job) -> None:
        if job.domain != "backup":
            logger.debug("Ignoring non-backup job: %s/%s", job.domain, job.operation)
            return
        if job.operation == "scheduled_backup":
            self._check_and_backup_if_due()
        else:
            logger.warning("Unknown backup operation: %s", job.operation)

    def _run(self) -> None:
        """Override _run to do initial startup check, then periodic checks."""
        logger.info("[%s] Worker loop started", self.name)

        # On startup, run an immediate check for overdue strategies
        self._check_and_backup_if_due()

        while not self._stop_event.is_set():
            now = _time.monotonic()
            if now - self._last_checked >= self.CHECK_INTERVAL:
                self._last_checked = now
                try:
                    self._check_and_backup_if_due()
                except Exception as exc:
                    logger.error(
                        "[%s] Backup check failed: %s", self.name, exc, exc_info=True
                    )
            # _stop_event.wait() returns immediately when the event is set,
            # so a 60-second wait still reacts instantly on shutdown.
            self._stop_event.wait(60.0)

        logger.info("[%s] Worker loop exited", self.name)

    def _check_and_backup_if_due(self) -> None:
        """Check all strategies and run backups for those that are due."""
        try:
            from lighterbird.core.backup import (
                backup_all_strategies,
                load_config,
                save_config,
            )

            cfg = load_config()
            strategies = cfg.get("strategies", [])
            now = datetime.now(UTC)
            triggered: list[str] = []

            for s in strategies:
                interval = s.get("interval_minutes", 0)
                if interval <= 0:
                    continue
                if not s.get("enabled", True):
                    continue

                last_raw = s.get("last_backup_at", "")
                if last_raw:
                    try:
                        last_dt = datetime.fromisoformat(last_raw)
                        elapsed = (now - last_dt).total_seconds() / 60.0
                    except (ValueError, TypeError):
                        elapsed = float("inf")
                else:
                    elapsed = float("inf")

                if elapsed >= interval:
                    logger.info(
                        "[backup] Strategy '%s' is due (%.1f min elapsed, interval %d min)",
                        s["id"], elapsed, interval,
                    )
                    triggered.append(s["id"])

            if triggered:
                logger.info("[backup] Running scheduled backup for: %s", triggered)
                backup_all_strategies()
                # Update last_backup_at for triggered strategies
                now_iso = now.isoformat()
                for s in cfg["strategies"]:
                    if s["id"] in triggered:
                        s["last_backup_at"] = now_iso
                save_config(cfg)
                logger.info("[backup] Scheduled backup complete for: %s", triggered)
        except Exception as exc:
            logger.error("[backup] Scheduler check error: %s", exc, exc_info=True)

    # Override start/stop so we don't use the queue mechanism for the backup scheduler
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=self.name,
            daemon=True,
        )
        self._thread.start()
        logger.info("[%s] Backup scheduler started", self.name)


__all__ = [
    "BackupScheduler",
    "CalDAVWorker",
    "EmailSyncWorker",
    "enqueue_caldav_push",
    "enqueue_caldav_sync",
    "enqueue_email_send",
    "enqueue_email_sync",
    "enqueue_email_trash",
    "get_worker_pool",
    "init_workers",
    "shutdown_workers",
    "start_idle_for_new_account",
    "stop_idle_for_account",
    "stop_all_idle",
]
