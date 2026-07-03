"""CalendarService — unified facade for calendar operations.

Composes CalendarCRUD and EventService.
"""

from __future__ import annotations

from lighterbird.calendar.services import CalendarCRUD, EventService
from lighterbird.calendar.db import get_db
from lighterbird.calendar.keyring import get_password, set_password, delete_password


class CalendarService:
    """Unified calendar operations facade."""

    def __init__(self, db=None):
        self.db = db or get_db()
        self.calendars = CalendarCRUD(self.db)
        self.events = EventService(self.db)

    # ── Calendar operations ──────────────────────────────────────────────

    def create_calendar(self, data: dict, password: str = "") -> dict:
        """Create a calendar. Password is stored in keyring if provided.

        Raises:
            RuntimeError: If a password was provided but the system keyring
                is unavailable or fails to store it.
        """
        cal = self.calendars.create(data)
        if password:
            if not set_password(cal["uuid"], password):
                self.calendars.delete(cal["uuid"])
                raise RuntimeError(
                    "System keyring is unavailable — cannot store calendar password. "
                    "Install a keyring backend (e.g. 'sudo apt install gnome-keyring'). "
                )
        return cal

    def list_calendars(self):
        return self.calendars.list()

    def delete_calendar(self, uuid_: str):
        delete_password(uuid_)
        return self.calendars.delete(uuid_)

    def resolve_calendar(self, ref: str):
        return self.calendars.resolve_uuid(ref)

    # ── CalDAV sync (pull only) ──────────────────────────────────────────

    def sync_calendar(self, uuid_: str) -> dict:
        """Pull events from a remote CalDAV calendar."""
        from lighterbird.calendar.caldav import fetch_remote_calendar_payloads
        from lighterbird.calendar.ics import insert_ics_events

        cal = self.calendars.get(uuid_)
        if not cal:
            raise ValueError(f"Calendar not found: {uuid_[:8]}")
        if not cal.get("remote"):
            return {"status": "local_calendar", "new_events": 0}

        url = cal.get("url", "")
        username = cal.get("username", "")
        password = get_password(uuid_)
        if not password and cal.get("remote"):
            raise ValueError(f"No password configured for calendar {uuid_[:8]}")

        results = fetch_remote_calendar_payloads(url, username, password)
        total_imported = 0
        for href, ics_data in results:
            added = insert_ics_events(
                self.db, uuid_, ics_data, remote_href=href,
            )
            total_imported += len(added)
        return {"status": "ok", "remote_events": len(results), "new_events": total_imported}

    def sync_all_calendars(self) -> dict[str, dict]:
        """Pull events from all remote calendars, then process push queue.

        Delegates to :meth:`sync_calendar` per calendar — errors (missing
        password, connection failure, etc.) are captured in each result's
        ``status`` field.
        """
        results = {}
        for cal in self.calendars.list():
            uuid_ = cal["uuid"]
            if not cal.get("remote"):
                results[uuid_] = {"status": "local_calendar"}
                continue
            try:
                results[uuid_] = self.sync_calendar(uuid_)
            except ValueError as e:
                results[uuid_] = {"status": "no_password", "error": str(e)}
            except Exception as e:
                results[uuid_] = {"status": "error", "error": str(e)}

        # Process any pending push/delete jobs in the sync queue
        try:
            self.events.process_sync_queue()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Calendar sync queue processing failed: %s", e,
            )

        return results

    # ── Event operations ─────────────────────────────────────────────────

    def create_event(self, data: dict) -> dict:
        return self.events.create(data)

    def list_events(self, start: str, end: str, calendar_uuid: str | None = None) -> list:
        cal_uuids = [calendar_uuid] if calendar_uuid else None
        return self.events.list_by_date_range(start, end, calendar_uuids=cal_uuids)

    def get_event(self, uuid_: str):
        return self.events.get(uuid_)

    def delete_event(self, uuid_: str) -> bool:
        return self.events.delete(uuid_)

    # ── ICS export / import ─────────────────────────────────────────────

    def export_ics(self, uuid: str | None = None, uuids: list[str] | None = None) -> str:
        """Export one or more events to an ICS calendar string.

        Args:
            uuid: Single event UUID.
            uuids: Multiple event UUIDs.

        Returns:
            ICS calendar text.
        """
        from lighterbird.calendar.ics import events_to_ics

        ids = []
        if uuid:
            ids.append(uuid)
        if uuids:
            ids.extend(uuids)

        rows = []
        for eid in ids:
            evt = self.events.get(eid)
            if evt:
                rows.append(dict(evt))
        if not rows:
            return ""
        return events_to_ics(rows)

    def import_ics(self, calendar_uuid: str, path: str) -> list[str]:
        """Import events from an ICS file.

        Args:
            calendar_uuid: Target calendar UUID.
            path: Path to the .ics file on disk.

        Returns:
            List of created event UUIDs.
        """
        from lighterbird.calendar.ics import insert_ics_events

        with open(path, "r") as f:
            text = f.read()
        return insert_ics_events(self.db, calendar_uuid, text)
