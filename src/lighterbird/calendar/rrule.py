"""RRULE (recurrence rule) utilities for calendar events.

Leverages ``dateutil.rrule`` for RFC 5545 RRULE parsing and expansion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from dateutil.rrule import rrulestr


def parse_rrule(rrule_str: str) -> str | None:
    """Validate and normalize an RRULE string.

    Args:
        rrule_str: RFC 5545 RRULE string (e.g. ``"FREQ=WEEKLY;BYDAY=MO,WE"``).

    Returns:
        The normalized RRULE string, or ``None`` if the input is empty.

    Raises:
        ValueError: If the RRULE string is syntactically invalid.
    """
    rrule_str = rrule_str.strip()
    if not rrule_str:
        return None
    if rrule_str.upper().startswith("RRULE:"):
        rrule_str = rrule_str[6:]
    try:
        rrulestr(f"DTSTART:20260101T000000Z\n{rrule_str}", dtstart=datetime.now(UTC))
        return rrule_str
    except Exception as e:
        raise ValueError(f"Invalid RRULE: {e}") from e


def expand_recurrences(
    event: dict[str, Any],
    range_start: str,
    range_end: str,
    max_instances: int = 365,
) -> list[dict[str, Any]]:
    """Expand a recurring event into instances within a date range.

    The original event dict is returned as-is if it has no ``rrule``.
    Instances are shallow copies of the original with adjusted
    ``start``, ``end``, and ``master_uuid`` fields.

    Args:
        event: Event dict with at least ``start``, ``end``, and ``rrule``.
        range_start: ISO date/datetime start of the query window.
        range_end: ISO date/datetime end of the query window.
        max_instances: Maximum number of expanded instances to generate.

    Returns:
        List of event dicts (the original event + generated instances).
    """
    rrule_str = (event.get("rrule") or "").strip()
    if not rrule_str:
        return [event]  # no recurrence

    event_uuid = event["uuid"]
    dtstart = _iso_to_dt(event["start"])
    dtend = _iso_to_dt(event["end"])
    duration = dtend - dtstart

    range_start_dt = _iso_to_dt(range_start)
    range_end_dt = _iso_to_dt(range_end)

    try:
        rule = rrulestr(
            f"DTSTART:{dtstart.strftime('%Y%m%dT%H%M%SZ')}\n{rrule_str}",
            dtstart=dtstart,
        )
    except Exception:
        return [event]  # invalid rrule, return as-is

    instances: list[dict[str, Any]] = []
    count = 0
    for occ_dt in rule:
        if occ_dt > range_end_dt:
            break
        occ_end = occ_dt + duration
        if occ_end < range_start_dt:
            continue
        if count >= max_instances:
            break
        if count == 0:
            # First occurrence is the original event itself
            instances.append(event)
        else:
            inst = dict(event)
            inst["uuid"] = f"{event_uuid}-{occ_dt.strftime('%Y%m%d')}"
            inst["start"] = _dt_to_iso(occ_dt)
            inst["end"] = _dt_to_iso(occ_end)
            inst["master_uuid"] = event_uuid
            inst["_recurring"] = True
            instances.append(inst)
        count += 1

    return instances


def _iso_to_dt(iso_str: str) -> datetime:
    """Convert an ISO 8601 string to a timezone-aware datetime."""
    dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _dt_to_iso(dt: datetime) -> str:
    """Convert a datetime to ISO 8601 string in UTC."""
    return dt.astimezone(UTC).replace(microsecond=0).isoformat()
