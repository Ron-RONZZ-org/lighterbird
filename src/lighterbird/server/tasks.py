"""Task orchestration — wires domain services to background workers.

Provides ``enqueue_*()`` functions called by route handlers and service
facades to offload work (sync, push) to background threads.
"""

from __future__ import annotations

import logging

from lighterbird.core.worker import BackgroundWorker, Job, WorkerPool

logger = logging.getLogger(__name__)

# ── Global worker pool (initialized by FastAPI lifespan) ──────────────────

_pool = WorkerPool()


def init_workers() -> WorkerPool:
    """Create, register, and start all background workers.

    Called from ``server/app.py`` lifespan startup.

    Returns:
        The configured :class:`WorkerPool` instance.
    """
    _pool.add("email", EmailSyncWorker("email-sync"))
    _pool.add("caldav", CalDAVWorker("caldav-sync"))
    _pool.start_all()
    logger.info("[tasks] All workers started")
    return _pool


def shutdown_workers(timeout: float = 5.0) -> None:
    """Stop all background workers.

    Called from ``server/app.py`` lifespan shutdown.

    Args:
        timeout: Max seconds to wait for active jobs to finish.
    """
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
    """BackgroundWorker subclass that handles email sync jobs."""

    def execute_job(self, job: Job) -> None:
        if job.domain != "email":
            logger.debug("Ignoring non-email job: %s/%s", job.domain, job.operation)
            return

        if job.operation == "sync":
            self._do_sync(job.payload)
        else:
            logger.warning("Unknown email operation: %s", job.operation)

    @staticmethod
    def _do_sync(payload: dict) -> None:
        """Run email sync — imports here to avoid circular deps."""
        from lighterbird.email.service import EmailService

        svc = EmailService()
        account_email = payload.get("account_email")
        if account_email:
            svc.sync_account(account_email)
        else:
            for account in svc.list_accounts():
                svc.sync_account(account["email"])


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
            CalendarService().sync_calendar(cal_uuid)

    @staticmethod
    def _do_push(payload: dict) -> None:
        """Push an event to a remote calendar."""
        from lighterbird.calendar.caldav import push_event
        from lighterbird.calendar.service import CalendarService
        from lighterbird.calendar.keyring import get_password
        from lighterbird.calendar.ics import events_to_ics

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
        from lighterbird.calendar.service import CalendarService
        from lighterbird.calendar.keyring import get_password

        cal_uuid = payload.get("calendar_uuid", "")
        event_uuid = payload.get("event_uuid", "")
        if not cal_uuid or not event_uuid:
            return

        svc = CalendarService()
        cal = svc.calendars.get(cal_uuid)
        if not cal:
            return

        event = svc.events.get(event_uuid)
        password = get_password(cal_uuid)
        remote_href = event.get("remote_href") if event else None

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


__all__ = [
    "init_workers",
    "shutdown_workers",
    "get_worker_pool",
    "enqueue_email_sync",
    "enqueue_caldav_push",
    "enqueue_caldav_sync",
    "EmailSyncWorker",
    "CalDAVWorker",
]
