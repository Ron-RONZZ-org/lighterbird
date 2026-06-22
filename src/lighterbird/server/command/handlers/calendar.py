"""Command handlers for the ``!calendar`` domain.

Registered paths:
    - calendar.list
    - calendar.event.add
    - calendar.event.view
    - calendar.event.modify
    - calendar.event.remove
    - calendar.event.search
    - calendar.account.add
    - calendar.account.list
    - calendar.account.modify
    - calendar.account.remove
    - calendar.sync
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.command.response import normalize_calendar, normalize_event
from lighterbird.server.deps import get_calendar_service
from lighterbird.calendar.service import CalendarService


# ── Handlers ────────────────────────────────────────────────────────────


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
    return {"type": "events", "title": "Events", "data": {"events": events}}


@command("calendar.event.add")
def event_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event add <calendar-uuid> <title> <start> <end> [location]"""
    if len(remaining) < 4:
        raise CommandValidationError(
            "Missing required params: <calendar-uuid> <title> <start> <end> [location]",
        )
    evt_data = {
        "kalendaro_uuid": remaining[0],
        "titolo": remaining[1],
        "komenco": remaining[2],
        "fino": remaining[3],
        "loko": remaining[4] if len(remaining) > 4 else "",
        "priskribo": "",
        "kategorio": "",
    }
    svc: CalendarService = get_calendar_service()
    evt = svc.create_event(evt_data)
    return {"type": "status", "title": "Event Created", "data": {"uuid": evt["uuid"], "title": evt["titolo"]}}


@command("calendar.event.view")
def event_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event view <uuid>"""
    if not remaining:
        raise CommandValidationError("Missing event UUID.", "Usage: !calendar event view <uuid>")
    svc: CalendarService = get_calendar_service()
    evt = svc.get_event(remaining[0])
    if not evt:
        raise CommandValidationError(f"Event not found: {remaining[0][:8]}")
    return {"type": "events", "title": evt.get("titolo", "(untitled)"), "data": normalize_event(evt)}


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
        updates["titolo"] = flags["title"]
    if "start" in flags:
        updates["komenco"] = flags["start"]
    if "end" in flags:
        updates["fino"] = flags["end"]
    if "location" in flags:
        updates["loko"] = flags["location"]
    if "description" in flags:
        updates["priskribo"] = flags["description"]
    if updates:
        svc.events.update(uuid, updates)
    return {"type": "status", "title": "Event Modified", "data": {"uuid": uuid[:8]}}


@command("calendar.event.remove")
def event_remove(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event remove <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError("Missing event UUID(s).", "Usage: !calendar event remove <uuid> [uuid...]")
    svc: CalendarService = get_calendar_service()
    removed = []
    for uuid in remaining:
        try:
            svc.delete_event(uuid)
            removed.append(uuid[:8])
        except Exception:
            pass
    return {"type": "status", "title": "Event(s) Removed", "data": {"removed": removed}}


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
    return {"type": "events", "title": "Search Results", "data": {"events": events}}


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


@command("calendar.account.remove")
def cal_account_remove(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar account remove <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError("Missing calendar UUID(s).", "Usage: !calendar account remove <uuid> [uuid...]")
    svc: CalendarService = get_calendar_service()
    removed = []
    for uuid in remaining:
        try:
            svc.delete_calendar(uuid)
            removed.append(uuid[:8])
        except Exception:
            pass
    return {"type": "status", "title": "Calendar(s) Removed", "data": {"removed": removed}}


@command("calendar.sync")
def cal_sync(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar sync [uuid]"""
    svc: CalendarService = get_calendar_service()
    if remaining:
        result = svc.sync_calendar(remaining[0])
        return {"type": "status", "title": "Calendar Synced", "data": result}
    results = svc.sync_all_calendars()
    return {"type": "status", "title": "All Calendars Synced", "data": results}
