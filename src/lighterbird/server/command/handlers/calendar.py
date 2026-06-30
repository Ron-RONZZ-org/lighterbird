"""Command handlers for the ``!calendar`` domain.

Registered paths:
    - calendar.list
    - calendar.event.add
    - calendar.event.view
    - calendar.event.modify
    - calendar.event.delete
    - calendar.event.search
    - calendar.account.add
    - calendar.account.list
    - calendar.account.modify
    - calendar.account.delete
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.command.response import normalize_calendar, normalize_event
from lighterbird.server.deps import get_calendar_service
from lighterbird.calendar.service import CalendarService


# ── Handlers ────────────────────────────────────────────────────────────


@command("calendar")
def calendar_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar — Show available calendar subcommands."""
    return {
        "type": "status",
        "title": "Calendar Commands",
        "data": {
            "_summary": (
                "Available !calendar commands:\n"
                "  !calendar list              — List events\n"
                "  !calendar event add         — Add an event\n"
                "  !calendar event view        — View an event\n"
                "  !calendar event modify      — Modify an event\n"
                "  !calendar event delete      — Delete an event\n"
                "  !calendar event search      — Search events\n"
                "  !calendar account list      — List calendars\n"
                "  !calendar account add       — Add a calendar\n"
                "  !calendar account modify    — Modify a calendar\n"
                "  !calendar account delete    — Delete a calendar\n"
                "  !calendar draft             — List / recall event drafts"
            ),
        },
    }


@command("calendar.list")
def calendar_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar list [start] [end] [--calendar uuid] [--query TEXT]"""
    svc: CalendarService = get_calendar_service()
    start = remaining[0] if len(remaining) > 0 else flags.get("start", "2000-01-01")
    end = remaining[1] if len(remaining) > 1 else flags.get("end", "2099-12-31")
    calendar_uuid = flags.get("calendar")
    query = flags.get("query")

    events = [normalize_event(e) for e in svc.list_events(start, end, calendar_uuid=calendar_uuid)]
    if query:
        q = query.lower()
        events = [
            e for e in events
            if q in (e.get("title") or "").lower()
            or q in (e.get("description") or "").lower()
        ]
    return {"type": "calendar-events", "title": "Events", "data": {"events": events}}


@command("calendar.event.add")
def event_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event add <title> <start> <end> [location] [--calendar UUID]

    Calendar UUID is specified via --calendar flag. If omitted and only
    one calendar exists, it is used automatically.
    """
    svc: CalendarService = get_calendar_service()

    # Resolve calendar UUID
    calendar_uuid = flags.get("calendar", "")
    if not calendar_uuid:
        calendars = svc.list_calendars()
        if len(calendars) == 1:
            calendar_uuid = calendars[0]["uuid"]
        elif len(calendars) == 0:
            raise CommandValidationError(
                "No calendars configured.",
                "Add one with: !calendar account add <url>",
            )
        else:
            raise CommandValidationError(
                "Multiple calendars. Specify one with --calendar <uuid>.",
                "Usage: !calendar event add \"Title\" \"2024-06-15T09:00\" \"2024-06-15T10:00\" --calendar <uuid>",
            )

    if len(remaining) < 3:
        raise CommandValidationError(
            "Missing required params: <title> <start> <end> [location]",
            "Usage: !calendar event add \"Title\" \"2024-06-15T09:00:00Z\" \"2024-06-15T10:00:00Z\" [location] --calendar <uuid>",
        )

    evt_data = {
        "calendar_uuid": calendar_uuid,
        "title": remaining[0],
        "start": remaining[1],
        "end": remaining[2],
        "location": remaining[3] if len(remaining) > 3 else "",
        "description": "",
        "category": "",
    }
    evt = svc.create_event(evt_data)
    return {"type": "status", "title": "Event Created", "data": {"uuid": evt["uuid"], "title": evt["title"]}}


@command("calendar.event.view")
def event_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event view <uuid>"""
    if not remaining:
        raise CommandValidationError("Missing event UUID.", "Usage: !calendar event view <uuid>")
    svc: CalendarService = get_calendar_service()
    evt = svc.get_event(remaining[0])
    if not evt:
        raise CommandValidationError(f"Event not found: {remaining[0][:8]}")
    return {"type": "events", "title": evt.get("title", "(untitled)"), "data": normalize_event(evt)}


@command("calendar.event.modify")
def event_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event modify <uuid> [--title TITLE] [--start ISO] [--end ISO] [--location LOC] [--description DESC]"""
    if not remaining:
        raise CommandValidationError("Missing event UUID.", "Usage: !calendar event modify <uuid> [--title ...]")
    uuid = remaining[0]
    svc: CalendarService = get_calendar_service()
    evt = svc.get_event(uuid)
    if not evt:
        raise CommandValidationError(f"Event not found: {uuid[:8]}")

    updates = {}
    if "title" in flags:
        updates["title"] = flags["title"]
    if "start" in flags:
        updates["start"] = flags["start"]
    if "end" in flags:
        updates["end"] = flags["end"]
    if "location" in flags:
        updates["location"] = flags["location"]
    if "description" in flags:
        updates["description"] = flags["description"]
    if updates:
        svc.events.update(uuid, updates)
    return {"type": "status", "title": "Event Modified", "data": {"uuid": uuid[:8]}}


@command("calendar.event.delete")
def event_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event delete <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError("Missing event UUID(s).", "Usage: !calendar event delete <uuid> [uuid...]")
    svc: CalendarService = get_calendar_service()
    removed = []
    for uuid in remaining:
        try:
            svc.delete_event(uuid)
            removed.append(uuid[:8])
        except Exception:
            pass
    return {"type": "status", "title": "Event(s) Deleted", "data": {"removed": removed}}


@command("calendar.event.search")
def event_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event search [--query TEXT] [--start DATE] [--end DATE] [--calendar UUID]"""
    svc: CalendarService = get_calendar_service()
    query = flags.get("query", " ".join(remaining) if remaining else "")
    start = flags.get("start", "2000-01-01")
    end = flags.get("end", "2099-12-31")
    calendar_uuid = flags.get("calendar")

    events = [normalize_event(e) for e in svc.list_events(start, end, calendar_uuid=calendar_uuid)]
    if query:
        q = query.lower()
        events = [
            e for e in events
            if q in (e.get("title") or "").lower()
            or q in (e.get("description") or "").lower()
        ]
    return {"type": "calendar-events", "title": "Search Results", "data": {"events": events}}


# ── Calendar account sub-commands ───────────────────────────────────────


@command("calendar.account.list")
def cal_account_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar account list"""
    svc: CalendarService = get_calendar_service()
    calendars = [normalize_calendar(c) for c in svc.list_calendars()]
    return {"type": "status", "title": "Calendars", "data": {"calendars": calendars}}


@command("calendar.account.add")
def cal_account_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar account add <url> [--username USER] [--password PW]"""
    if not remaining:
        raise CommandValidationError("Missing calendar URL.", "Usage: !calendar account add <url> [--username ...] [--password ...]")
    url = remaining[0]
    username = flags.get("username", remaining[1] if len(remaining) > 1 else "")
    password = flags.get("password", remaining[2] if len(remaining) > 2 else "")
    svc: CalendarService = get_calendar_service()
    cal_data = {"url": url, "username": username, "remote": 1}
    cal = svc.create_calendar(cal_data, password=password)
    return {"type": "status", "title": "Calendar Added", "data": {"uuid": cal["uuid"], "url": url}}


@command("calendar.account.modify")
def cal_account_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar account modify <uuid> [--url URL] [--username USER] [--password PW]"""
    if not remaining:
        raise CommandValidationError("Missing calendar UUID.", "Usage: !calendar account modify <uuid> [--url ...]")
    uuid = remaining[0]
    svc: CalendarService = get_calendar_service()
    updates = {}
    if "url" in flags:
        updates["url"] = flags["url"]
    if "username" in flags:
        updates["username"] = flags["username"]
    if updates:
        svc.calendars.update(uuid, updates)
    if "password" in flags:
        from lighterbird.calendar.keyring import set_password
        set_password(uuid, flags["password"])
    return {"type": "status", "title": "Calendar Modified", "data": {"uuid": uuid[:8]}}


@command("calendar.account.delete")
def cal_account_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar account delete <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError("Missing calendar UUID(s).", "Usage: !calendar account delete <uuid> [uuid...]")
    svc: CalendarService = get_calendar_service()
    removed = []
    for uuid in remaining:
        try:
            svc.delete_calendar(uuid)
            removed.append(uuid[:8])
        except Exception:
            pass
    return {"type": "status", "title": "Calendar(s) Deleted", "data": {"removed": removed}}
