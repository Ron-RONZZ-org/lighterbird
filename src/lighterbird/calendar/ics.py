"""ICS (iCalendar) parsing and generation utilities.

Forked from A-organizi's utils/ics.py.
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import UTC, datetime
from typing import Any


def iter_ics_events(text: str) -> list[dict[str, str]]:
    """Parse ICS calendar text and extract VEVENT entries.

    Each VEVENT is returned as a dict with uppercase keys
    (DTSTART, DTEND, SUMMARY, LOCATION, etc.).

    Args:
        text: Raw ICS file content.

    Returns:
        List of event dicts.
    """
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.split(";", 1)[0].upper()
        current[key] = value.strip()
    return events


def ics_dt(value: str) -> datetime:
    """Parse an ICS datetime string into a timezone-aware datetime.

    Supports:
    - ``YYYYMMDDTHHMMSSZ`` (UTC)
    - ``YYYYMMDDTHHMMSS`` (local, treated as UTC)
    - ``YYYYMMDD`` (all-day, treated as UTC midnight)
    """
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    if "T" in value:
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
    return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)


def _to_iso(dt: datetime) -> str:
    """Convert a datetime to ISO 8601 string in UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0).isoformat()


def events_to_ics(rows: list[dict[str, Any]]) -> str:
    """Generate ICS calendar text from event rows."""
    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//lighterbird//calendar//EN",
    ]
    for row in rows:
        start_dt = datetime.fromisoformat(str(row["start"]).replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(str(row["end"]).replace("Z", "+00:00"))
        start = start_dt.strftime("%Y%m%dT%H%M%SZ")
        end = end_dt.strftime("%Y%m%dT%H%M%SZ")
        out.extend([
            "BEGIN:VEVENT",
            f"UID:{row['uuid']}",
            f"SUMMARY:{row.get('title') or ''!s}",
            f"DTSTART:{start}",
            f"DTEND:{end}",
            f"LOCATION:{row.get('location') or ''!s}",
            f"CATEGORIES:{row.get('category') or ''!s}",
            f"DESCRIPTION:{row.get('description') or ''!s}",
            "END:VEVENT",
        ])
    out.append("END:VCALENDAR")
    return "\n".join(out) + "\n"


def event_exists(
    db, calendar_uuid: str, title: str, start_iso: str, end_iso: str,
) -> bool:
    """Check if an event with the same details already exists."""
    row = db.execute_one(
        "SELECT 1 FROM events "
        "WHERE calendar_uuid = ? AND title = ? AND start = ? AND end = ?",
        (calendar_uuid, title, start_iso, end_iso),
    )
    return row is not None


def insert_ics_events(
    db, calendar_uuid: str, text: str, *, now: str | None = None,
    remote_href: str | None = None,
) -> list[str]:
    """Parse ICS text and insert events into the database.

    Skips duplicates (same calendar_uuid + title + start + end).
    Uses the remote UID (from ICS UID property) as the local UUID when
    available, preserving identity for two-way sync. Stores *remote_href*
    so that subsequent PUT/DELETE operations know the server URL.

    Args:
        db: Database handle.
        calendar_uuid: Local calendar UUID.
        text: Raw ICS content.
        now: Optional timestamp override.
        remote_href: Server-provided resource path (from multistatus REPORT).

    Returns:
        List of newly inserted (or updated) event UUIDs.
    """
    ts = now or datetime.now(UTC).replace(microsecond=0).isoformat()
    added: list[str] = []
    for event in iter_ics_events(text):
        start = _to_iso(ics_dt(str(event.get("DTSTART", ts))))
        end = _to_iso(ics_dt(str(event.get("DTEND", event.get("DTSTART", ts)))))
        title = str(event.get("SUMMARY", ""))
        uid = str(event.get("UID", ""))
        if not uid:
            uid = str(uuid_mod.uuid4())

        # Check if event with this UID already exists
        existing = None
        if uid:
            existing = db.execute_one(
                "SELECT uuid, remote_href FROM events WHERE uuid = ? AND calendar_uuid = ?",
                (uid, calendar_uuid),
            )

        if existing:
            # Update remote_href if not yet set
            if remote_href and not existing["remote_href"]:
                db.execute(
                    "UPDATE events SET remote_href = ?, updated_at = ? WHERE uuid = ?",
                    (remote_href, ts, uid),
                )
            continue

        # Check content-based dedup
        if event_exists(db, calendar_uuid, title, start, end):
            continue

        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO events ("
                "uuid, calendar_uuid, title, start, end, "
                "category, location, description, remote_href, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    uid, calendar_uuid, title, start, end,
                    str(event.get("CATEGORIES", "")),
                    str(event.get("LOCATION", "")),
                    str(event.get("DESCRIPTION", "")),
                    remote_href or "",
                    ts, ts,
                ),
            )
        added.append(uid)
    return added
