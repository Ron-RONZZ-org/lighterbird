"""LLM tools for the calendar domain.

Tools:
    - ``calendar.find`` -- Search events by date range, title, or location
    - ``calendar.read`` -- Full event details by UUID
    - ``calendar.create`` -- Create a new calendar event
    - ``calendar.update`` -- Modify an existing event
    - ``calendar.delete`` -- Delete an event
    - ``calendar.accounts.find`` -- List calendar accounts
    - ``calendar.accounts.read`` -- Get account details by UUID
    - ``calendar.accounts.create`` -- Add a CalDAV account
    - ``calendar.accounts.update`` -- Modify an account
    - ``calendar.accounts.delete`` -- Remove a calendar account
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lightercore.permissions import PermissionLevel

from lighterbird.server.deps import get_calendar_service
from lighterbird.server.llm.tools import llm_tool


def _parse_iso(value: str | None) -> str | None:
    """Normalize an ISO date string."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return value


# ── Find events ───────────────────────────────────────────────────────────────


@llm_tool(
    name="calendar.find",
    description="Search calendar events within a date range, optionally filtered by title or location.",
    params=[
        {"name": "after_date", "type": "string", "description": "Start of date range (ISO, e.g. '2026-01-01')", "required": True},
        {"name": "before_date", "type": "string", "description": "End of date range (ISO, e.g. '2026-12-31')", "required": True},
        {"name": "query", "type": "string", "description": "Search term for title or location"},
        {"name": "calendar_uuid", "type": "string", "description": "Specific calendar UUID to search"},
        {"name": "max_results", "type": "number", "description": "Maximum results (default 50)"},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_calendar_find(**kwargs: Any) -> dict:
    """Search events in a date range."""
    start = _parse_iso(kwargs.get("after_date")) or ""
    end = _parse_iso(kwargs.get("before_date")) or ""
    if not start or not end:
        return {"success": False, "error": "after_date and before_date are required"}

    service = get_calendar_service()
    try:
        events = service.list_events(start, end, calendar_uuid=kwargs.get("calendar_uuid"))
        limit = int(kwargs.get("max_results", 50))
        query = (kwargs.get("query") or "").lower()

        results = []
        for e in events:
            if query:
                title = (e.get("title") or "").lower()
                location = (e.get("location") or "").lower()
                if query not in title and query not in location:
                    continue
            results.append({
                "uuid": e.get("uuid", ""),
                "title": e.get("title", ""),
                "start": e.get("start", ""),
                "end": e.get("end", ""),
                "location": e.get("location", ""),
                "description_preview": (e.get("description") or "")[:200],
            })
            if len(results) >= limit:
                break

        return {"success": True, "data": results, "total": len(results)}
    except Exception as exc:
        return {"success": False, "error": f"Calendar search failed: {exc}"}


# ── Read event ────────────────────────────────────────────────────────────────


@llm_tool(
    name="calendar.read",
    description="Get full event details by UUID, including description and recurrence info.",
    params=[
        {"name": "uuid", "type": "string", "description": "Event UUID", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_calendar_read(uuid: str = "") -> dict:
    """Get full event details."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_calendar_service()
    try:
        event = service.get_event(uuid)
        if not event:
            return {"success": False, "error": f"Event not found: {uuid}"}
        return {"success": True, "data": dict(event)}
    except Exception as exc:
        return {"success": False, "error": f"Failed to read event: {exc}"}


# ── Create event ──────────────────────────────────────────────────────────────


@llm_tool(
    name="calendar.create",
    description="Create a new calendar event with title, start/end times, and optional location or description.",
    params=[
        {"name": "calendar_uuid", "type": "string", "description": "Calendar UUID to create the event in", "required": True},
        {"name": "title", "type": "string", "description": "Event title", "required": True},
        {"name": "start", "type": "string", "description": "Start datetime (ISO 8601)", "required": True},
        {"name": "end", "type": "string", "description": "End datetime (ISO 8601)", "required": True},
        {"name": "description", "type": "string", "description": "Event description or notes"},
        {"name": "location", "type": "string", "description": "Event location"},
        {"name": "all_day", "type": "boolean", "description": "Whether this is an all-day event"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_calendar_create(**kwargs: Any) -> dict:
    """Create a new event."""
    calendar_uuid = kwargs.get("calendar_uuid", "")
    title = kwargs.get("title", "")
    start = _parse_iso(kwargs.get("start")) or ""
    end = _parse_iso(kwargs.get("end")) or ""

    if not calendar_uuid:
        return {"success": False, "error": "calendar_uuid is required"}
    if not title:
        return {"success": False, "error": "title is required"}
    if not start or not end:
        return {"success": False, "error": "start and end are required (ISO 8601 format)"}

    data: dict[str, Any] = {
        "calendar_uuid": calendar_uuid,
        "title": title,
        "start": start,
        "end": end,
        "description": kwargs.get("description", ""),
        "location": kwargs.get("location", ""),
        "all_day": bool(kwargs.get("all_day", False)),
    }

    service = get_calendar_service()
    try:
        result = service.create_event(data)
        return {"success": True, "data": {"uuid": result.get("uuid", ""), "title": title}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to create event: {exc}"}


# ── Update event ──────────────────────────────────────────────────────────────


@llm_tool(
    name="calendar.update",
    description="Modify an existing calendar event. Only provided fields are updated.",
    params=[
        {"name": "uuid", "type": "string", "description": "Event UUID to modify", "required": True},
        {"name": "title", "type": "string", "description": "New event title"},
        {"name": "start", "type": "string", "description": "New start datetime (ISO 8601)"},
        {"name": "end", "type": "string", "description": "New end datetime (ISO 8601)"},
        {"name": "description", "type": "string", "description": "New description"},
        {"name": "location", "type": "string", "description": "New location"},
        {"name": "all_day", "type": "boolean", "description": "Whether this is an all-day event"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_calendar_update(**kwargs: Any) -> dict:
    """Modify an event."""
    uuid = kwargs.get("uuid", "")
    if not uuid:
        return {"success": False, "error": "uuid is required"}

    data: dict[str, Any] = {}
    if kwargs.get("title") is not None:
        data["title"] = kwargs["title"]
    if kwargs.get("start") is not None:
        data["start"] = _parse_iso(kwargs["start"]) or kwargs["start"]
    if kwargs.get("end") is not None:
        data["end"] = _parse_iso(kwargs["end"]) or kwargs["end"]
    if kwargs.get("description") is not None:
        data["description"] = kwargs["description"]
    if kwargs.get("location") is not None:
        data["location"] = kwargs["location"]
    if kwargs.get("all_day") is not None:
        data["all_day"] = bool(kwargs["all_day"])

    if not data:
        return {"success": False, "error": "No fields to update"}

    service = get_calendar_service()
    try:
        result = service.events.update(uuid, data)
        if not result:
            return {"success": False, "error": f"Event not found: {uuid}"}
        return {"success": True, "data": {"uuid": uuid, "updated": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to update event: {exc}"}


# ── Delete event ──────────────────────────────────────────────────────────────


@llm_tool(
    name="calendar.delete",
    description="Delete a calendar event by UUID.",
    params=[
        {"name": "uuid", "type": "string", "description": "Event UUID to delete", "required": True},
    ],
    permission_level=PermissionLevel.DESTRUCTIVE,
)
def llm_calendar_delete(uuid: str = "") -> dict:
    """Delete an event."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_calendar_service()
    try:
        ok = service.delete_event(uuid)
        if not ok:
            return {"success": False, "error": f"Event not found: {uuid}"}
        return {"success": True, "data": {"uuid": uuid, "deleted": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to delete event: {exc}"}


# ═══════════════════════════════════════════════════════════════════════════════
# Calendar Account management (CalDAV)
# ═══════════════════════════════════════════════════════════════════════════════


@llm_tool(
    name="calendar.accounts.find",
    description="List all configured calendar accounts with their basic info.",
    params=[
        {"name": "max_results", "type": "number", "description": "Maximum results (default 50)"},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_calendar_accounts_find(**kwargs: Any) -> dict:
    """List all calendars (accounts)."""
    service = get_calendar_service()
    try:
        cals = service.list_calendars()
        limit = int(kwargs.get("max_results", 50))
        return {"success": True, "data": (cals or [])[:limit], "total": len(cals or [])}
    except Exception as exc:
        return {"success": False, "error": f"Failed to list calendars: {exc}"}


@llm_tool(
    name="calendar.accounts.read",
    description="Get details for a specific calendar account by UUID.",
    params=[
        {"name": "uuid", "type": "string", "description": "Calendar UUID", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_calendar_accounts_read(uuid: str = "") -> dict:
    """Get calendar account details."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_calendar_service()
    try:
        cal = service.calendars.get(uuid)
        if not cal:
            return {"success": False, "error": f"Calendar not found: {uuid}"}
        return {"success": True, "data": dict(cal)}
    except Exception as exc:
        return {"success": False, "error": f"Failed to get calendar: {exc}"}


@llm_tool(
    name="calendar.accounts.create",
    description="Add a new calendar account (CalDAV or local).",
    params=[
        {"name": "name", "type": "string", "description": "Display name for the calendar", "required": True},
        {"name": "url", "type": "string", "description": "CalDAV URL (omit for local-only calendar)"},
        {"name": "username", "type": "string", "description": "CalDAV username"},
        {"name": "password", "type": "string", "description": "CalDAV password"},
        {"name": "color", "type": "string", "description": "Calendar color (hex or name)"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_calendar_accounts_create(**kwargs: Any) -> dict:
    """Add a new calendar."""
    name = kwargs.get("name", "")
    if not name:
        return {"success": False, "error": "name is required"}

    data: dict[str, Any] = {
        "name": name,
        "url": kwargs.get("url", ""),
        "username": kwargs.get("username", ""),
        "color": kwargs.get("color", ""),
        "remote": bool(kwargs.get("url")),
    }

    password = kwargs.get("password", "")
    service = get_calendar_service()
    try:
        result = service.create_calendar(data, password=password)
        return {"success": True, "data": {"uuid": result.get("uuid", "")}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to create calendar: {exc}"}


@llm_tool(
    name="calendar.accounts.update",
    description="Modify an existing calendar account's settings.",
    params=[
        {"name": "uuid", "type": "string", "description": "Calendar UUID to modify", "required": True},
        {"name": "name", "type": "string", "description": "New display name"},
        {"name": "url", "type": "string", "description": "New CalDAV URL"},
        {"name": "username", "type": "string", "description": "New username"},
        {"name": "password", "type": "string", "description": "New password"},
        {"name": "color", "type": "string", "description": "New calendar color"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_calendar_accounts_update(**kwargs: Any) -> dict:
    """Modify a calendar."""
    uuid = kwargs.get("uuid", "")
    if not uuid:
        return {"success": False, "error": "uuid is required"}

    data: dict[str, Any] = {}
    if kwargs.get("name") is not None:
        data["name"] = kwargs["name"]
    if kwargs.get("url") is not None:
        data["url"] = kwargs["url"]
    if kwargs.get("username") is not None:
        data["username"] = kwargs["username"]
    if kwargs.get("color") is not None:
        data["color"] = kwargs["color"]

    if not data:
        return {"success": False, "error": "No fields to update"}

    service = get_calendar_service()
    try:
        result = service.calendars.update(uuid, data)
        if not result:
            return {"success": False, "error": f"Calendar not found: {uuid}"}
        return {"success": True, "data": {"uuid": uuid, "updated": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to update calendar: {exc}"}


@llm_tool(
    name="calendar.accounts.delete",
    description="Permanently remove a calendar account and all its events.",
    params=[
        {"name": "uuid", "type": "string", "description": "Calendar UUID to delete", "required": True},
    ],
    permission_level=PermissionLevel.DESTRUCTIVE,
)
def llm_calendar_accounts_delete(uuid: str = "") -> dict:
    """Delete a calendar permanently."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_calendar_service()
    try:
        service.delete_calendar(uuid)
        return {"success": True, "data": {"uuid": uuid, "deleted": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to delete calendar: {exc}"}
