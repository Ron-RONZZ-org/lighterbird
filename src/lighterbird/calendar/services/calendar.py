"""Calendar and event services.

Flat service classes, forked from A-organizi's service/kalendaro.py.
Stripped of CalDAV sync hooks for MVP (local-only events).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from lighterbird.core.backoff import compute_backoff_seconds
from lighterbird.core.crud import CRUDService


class CalendarCRUD(CRUDService):
    """CRUD service for calendars (calendars)."""

    def __init__(self, db):
        super().__init__(db, "calendars")

    def find_by_uuid_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        return super().find_by_uuid_prefix(prefix.lstrip("#"), limit=limit)

    def resolve_uuid(self, ref: str) -> str | None:
        """Resolve a user reference to a calendar UUID."""
        token = ref.lstrip("#")
        row = self.db.execute_one("SELECT uuid FROM calendars WHERE uuid = ?", (token,))
        if row:
            return str(row["uuid"])
        rows = self.db.execute(
            "SELECT uuid FROM calendars WHERE uuid LIKE ? ORDER BY uuid",
            (f"{token}%",),
        )
        if len(rows) == 1:
            return str(rows[0]["uuid"])
        return None

    def calendar_exists(self, url: str, username: str) -> bool:
        """Check if a calendar with the given URL and username exists."""
        row = self.db.execute_one(
            "SELECT 1 FROM calendars WHERE LOWER(url)=LOWER(?) AND LOWER(username)=LOWER(?)",
            (url.strip(), username.strip()),
        )
        return row is not None

    def delete(self, uuid_: str, soft: bool = True) -> bool:
        """Delete a calendar and all its events."""
        with self.db.transaction() as conn:
            conn.execute("DELETE FROM events WHERE calendar_uuid = ?", (uuid_,))
            conn.execute("DELETE FROM calendars WHERE uuid = ?", (uuid_,))
        return True


class EventService(CRUDService):
    """CRUD service for events (events) with date-range queries."""

    def __init__(self, db):
        super().__init__(db, "events")

    def find_by_uuid_prefix(self, prefix: str, limit: int = 10) -> list[dict[str, Any]]:
        return super().find_by_uuid_prefix(prefix.lstrip("#"), limit=limit)

    # ── Two-way CalDAV sync hooks ──────────────────────────────────────

    def _get_calendar(self, event_uuid: str) -> dict[str, Any] | None:
        """Get the calendar for an event, or None."""
        row = self.db.execute_one(
            "SELECT c.uuid, c.url, c.remote FROM calendars c "
            "JOIN events e ON e.calendar_uuid = c.uuid "
            "WHERE e.uuid = ?", (event_uuid,)
        )
        return row

    def _enqueue_sync(
        self, event_uuid: str, operation: str, *,
        remote_href: str | None = None,
        calendar_uuid: str | None = None,
    ) -> None:
        """Queue a push/delete sync job for a remote calendar event.

        Args:
            event_uuid: The event's UUID.
            operation: ``"push"`` or ``"delete"``.
            remote_href: Server-provided resource path (if known).
            calendar_uuid: The calendar UUID (avoids JOIN lookups that
                fail when the event has already been deleted).
        """
        if calendar_uuid:
            cal = self.db.execute_one(
                "SELECT uuid, url, remote FROM calendars WHERE uuid = ?",
                (calendar_uuid,),
            )
        else:
            cal = self._get_calendar(event_uuid)
        if not cal or not cal.get("remote") or not cal.get("url"):
            return  # local-only calendar, no sync needed
        now = datetime.now(UTC).isoformat()
        self.db.execute(
            "INSERT INTO calendar_sync_queue "
            "(calendar_uuid, event_uuid, operation, remote_href, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
            (cal["uuid"], event_uuid, operation, remote_href or "", now, now),
        )

    def _post_create(self, data: dict, result: dict) -> None:
        """After creating an event, queue a push to the remote server."""
        event_uuid = result.get("uuid", "")
        cal_uuid = result.get("calendar_uuid", data.get("calendar_uuid", ""))
        if event_uuid:
            self._enqueue_sync(event_uuid, "push", calendar_uuid=cal_uuid)

    def _post_update(self, pk: str, old_data: dict | None, new_data: dict) -> None:
        """After updating an event, queue a push to the remote server."""
        if old_data:
            self._enqueue_sync(
                pk, "push",
                remote_href=old_data.get("remote_href", ""),
                calendar_uuid=old_data.get("calendar_uuid", ""),
            )

    def _post_delete(self, pk: str, old_data: dict | None) -> None:
        """After deleting an event, queue a remote DELETE."""
        if old_data:
            self._enqueue_sync(
                pk, "delete",
                remote_href=old_data.get("remote_href", ""),
                calendar_uuid=old_data.get("calendar_uuid", ""),
            )

    def _update_remote_href(self, event_uuid: str, remote_href: str) -> None:
        """Store the remote_href returned after a successful push."""
        self.db.execute(
            "UPDATE events SET remote_href = ?, updated_at = ? WHERE uuid = ?",
            (remote_href, datetime.now(UTC).isoformat(), event_uuid),
        )

    def process_sync_queue(self, limit: int = 50) -> list[dict[str, Any]]:
        """Process pending and retryable sync jobs with exponential backoff.

        Queries for jobs that are either:
        * ``status = 'pending'`` — fresh jobs, retried immediately.
        * ``status = 'failed'`` AND ``next_attempt <= now`` AND
          ``retries < max_retries`` — retryable jobs.

        On success: status becomes ``'completed'``.
        On failure: ``retries`` is incremented, ``next_attempt`` is set
        with exponential backoff (60s, 2min, 4min, … up to 24h).
        After ``max_retries`` exhausted: stays ``'failed'`` permanently.

        Args:
            limit: Maximum number of jobs to process this call.

        Returns:
            List of job result dicts with id, event, status, and optional error.
        """
        from lighterbird.calendar.caldav import (
            delete_event,
            push_event,
            remote_http_url,
        )
        from lighterbird.calendar.ics import events_to_ics
        from lighterbird.calendar.keyring import get_password

        now_ts = datetime.now(UTC)
        now_iso = now_ts.isoformat()

        jobs = list(self.db.execute(
            """SELECT * FROM calendar_sync_queue
               WHERE (status = 'pending'
                      OR (status = 'failed'
                          AND retries < max_retries
                          AND (next_attempt IS NULL OR next_attempt <= ?)))
               ORDER BY id ASC
               LIMIT ?""",
            (now_iso, limit),
        ))

        results: list[dict[str, Any]] = []

        for job in jobs:
            job_id = job["id"]
            event_uuid = job["event_uuid"]
            operation = job["operation"]
            cal_uuid = job["calendar_uuid"]
            remote_href = job.get("remote_href") or None
            retries = job.get("retries", 0)
            max_retries = job.get("max_retries", 5)

            try:
                # Mark as running
                self.db.execute(
                    "UPDATE calendar_sync_queue SET status = 'running', updated_at = ? WHERE id = ?",
                    (now_iso, job_id),
                )

                # Get calendar config
                cal = self.db.execute_one(
                    "SELECT * FROM calendars WHERE uuid = ?", (cal_uuid,)
                )
                if not cal:
                    raise RuntimeError(f"Calendar not found: {cal_uuid[:8]}")

                url = remote_http_url(cal.get("url", ""))
                username = cal.get("username", "")
                password = get_password(cal_uuid) or ""

                if operation == "push":
                    event = self.db.execute_one(
                        "SELECT * FROM events WHERE uuid = ?", (event_uuid,)
                    )
                    if event:
                        ics_payload = events_to_ics([dict(event)])
                        push_event(
                            url, username, password, ics_payload,
                            event_uuid, remote_href,
                        )
                        new_href = remote_href or f"{url.rstrip('/')}/{event_uuid}.ics"
                        if not event.get("remote_href"):
                            self._update_remote_href(event_uuid, new_href)
                elif operation == "delete":
                    delete_event(url, username, password, event_uuid, remote_href)

                # Mark completed
                self.db.execute(
                    "UPDATE calendar_sync_queue SET status = 'completed', updated_at = ? WHERE id = ?",
                    (now_iso, job_id),
                )
                results.append({"id": job_id, "event": event_uuid[:8], "status": "completed"})

            except Exception as exc:
                err_msg = str(exc)
                new_retries = retries + 1
                if new_retries >= max_retries:
                    # Exhausted — stay permanently failed
                    self.db.execute(
                        "UPDATE calendar_sync_queue SET status = 'failed', "
                        "retries = ?, error = ?, updated_at = ? WHERE id = ?",
                        (new_retries, err_msg, now_iso, job_id),
                    )
                    results.append({
                        "id": job_id, "event": event_uuid[:8],
                        "status": "failed", "error": err_msg,
                        "permanent": True,
                    })
                else:
                    # Schedule next attempt with exponential backoff
                    delay = compute_backoff_seconds(new_retries - 1, base_seconds=60)
                    next_attempt = (now_ts + timedelta(seconds=delay)).isoformat()
                    self.db.execute(
                        "UPDATE calendar_sync_queue SET status = 'failed', "
                        "retries = ?, next_attempt = ?, error = ?, updated_at = ? "
                        "WHERE id = ?",
                        (new_retries, next_attempt, err_msg, now_iso, job_id),
                    )
                    results.append({
                        "id": job_id, "event": event_uuid[:8],
                        "status": "retrying", "error": err_msg,
                        "retry_in_seconds": delay,
                        "retries": new_retries,
                    })

        return results

    def list_by_date_range(
        self,
        start: str,
        end: str,
        calendar_uuids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List events in a date range, optionally filtered by calendar."""
        params: list[Any] = [start, end]
        query = "SELECT * FROM events WHERE date(start) >= ? AND date(start) <= ?"
        if calendar_uuids:
            placeholders = ",".join("?" for _ in calendar_uuids)
            query += f" AND calendar_uuid IN ({placeholders})"
            params.extend(calendar_uuids)
        query += " ORDER BY start ASC"
        return self.db.execute(query, tuple(params))
