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

from lightercore.permissions import PermissionLevel

from lighterbird.calendar.service import CalendarService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_calendar_service

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
                "  !calendar event export ics  — Export event(s) as ICS\n"
                "  !calendar event import ics  — Import events from ICS file or email\n"
                "  !calendar event rrule       — Manage event recurrence rules\n"
                "  !calendar sync-status       — Show CalDAV sync queue\n"
                "  !calendar account list      — List calendars\n"
                "  !calendar account add       — Add a calendar\n"
                "  !calendar account modify    — Modify a calendar\n"
                "  !calendar account delete    — Delete a calendar\n"
                "  !calendar draft             — List / recall event drafts"
            ),
        },
    }


@command("calendar.list", permission_level=PermissionLevel.READ)
def calendar_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar list [start] [end] [--calendar uuid] [--query TEXT]"""
    svc: CalendarService = get_calendar_service()
    start = remaining[0] if len(remaining) > 0 else flags.get("start", "2000-01-01")
    end = remaining[1] if len(remaining) > 1 else flags.get("end", "2099-12-31")
    calendar_uuid = flags.get("calendar")
    query = flags.get("query")

    events = [dict(e) for e in svc.list_events(start, end, calendar_uuid=calendar_uuid)]
    if query:
        q = query.lower()
        events = [
            e for e in events
            if q in (e.get("title") or "").lower()
            or q in (e.get("description") or "").lower()
        ]
    return {"type": "calendar-events", "title": "Events", "data": {"events": events}}


@command("calendar.event.add", interactive=True)
def event_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event add <title> <start> <end> [location] [--calendar UUID]
                                   [--rrule FREQ=WEEKLY;BYDAY=MO,WE]

    Calendar UUID is specified via --calendar flag. If omitted and only
    one calendar exists, it is used automatically.

    Recurrence rules (RFC 5545):
      --rrule FREQ=DAILY                  Every day
      --rrule FREQ=WEEKLY;BYDAY=MO,WE,FR  Mon/Wed/Fri
      --rrule FREQ=WEEKLY;INTERVAL=2      Every 2 weeks
      --rrule FREQ=MONTHLY;BYDAY=1MO      First Monday each month
      --rrule FREQ=YEARLY                 Yearly
      --rrule FREQ=DAILY;COUNT=10         Every day, 10 occurrences
      --rrule FREQ=DAILY;UNTIL=2026-12-31 Until a date
    """
    from lighterbird.calendar.rrule import parse_rrule

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

    rrule_str = flags.get("rrule", "")
    if rrule_str:
        try:
            rrule_str = parse_rrule(rrule_str) or ""
        except ValueError as e:
            raise CommandValidationError(str(e))

    evt_data = {
        "calendar_uuid": calendar_uuid,
        "title": remaining[0],
        "start": remaining[1],
        "end": remaining[2],
        "location": remaining[3] if len(remaining) > 3 else "",
        "description": remaining[4] if len(remaining) > 4 else "",
        "category": "",
        "rrule": rrule_str,
    }
    evt = svc.create_event(evt_data)
    return {"type": "status", "title": "Event Created", "data": {"uuid": evt["uuid"], "title": evt["title"], "rrule": evt.get("rrule", "") or "(none)"}}


@command("calendar.event.view", permission_level=PermissionLevel.READ,
         params=[{"name": "uuid", "type": "string", "help": "Event UUID", "required": True, "uuidSource": "calendar.events"}])
def event_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event view <uuid>"""
    if not remaining:
        raise CommandValidationError("Missing event UUID.", "Usage: !calendar event view <uuid>")
    svc: CalendarService = get_calendar_service()
    evt = svc.get_event(remaining[0])
    if not evt:
        raise CommandValidationError(f"Event not found: {remaining[0][:8]}")
    return {"type": "events", "title": evt.get("title", "(untitled)"), "data": dict(evt)}


@command("calendar.event.modify",
         params=[{"name": "uuid", "type": "string", "help": "Event UUID", "required": True, "uuidSource": "calendar.events"}])
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
    return {"type": "status", "title": "Event Modified", "data": {"uuid": uuid}}


@command("calendar.event.delete", permission_level=PermissionLevel.DESTRUCTIVE, interactive=True,
         params=[{"name": "uuid", "type": "string", "help": "Event UUID(s)", "required": True, "uuidSource": "calendar.events", "repeatable": True}])
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


@command("calendar.event.export.ics", permission_level=PermissionLevel.READ,
         params=[{"name": "uuid", "type": "string", "help": "Event UUID(s)", "required": True, "uuidSource": "calendar.events", "repeatable": True}])
def event_export_ics(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event export ics <uuid> [<uuid>...]"""
    if not remaining:
        raise CommandValidationError("Missing event UUID(s).", "Usage: !calendar event export ics <uuid> [uuid...]")
    svc: CalendarService = get_calendar_service()
    ics_text = svc.export_ics(uuids=remaining)
    return {"type": "status", "title": "ICS Export", "data": {"ics": ics_text, "count": ics_text.count("BEGIN:VEVENT")}}


@command("calendar.event.import.ics")
def event_import_ics(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event import ics <path|from-email msg-uuid> [--calendar UUID]

    Import events from an ICS file or from an email attachment.
    Use ``!calendar event import ics from-email <msg-uuid>`` to
    import .ics attachments from an email message.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing argument.",
            "Usage: !calendar event import ics <path>\n"
            "       !calendar event import ics from-email <msg-uuid>",
        )

    svc: CalendarService = get_calendar_service()
    calendar_uuid = flags.get("calendar", "")
    if not calendar_uuid:
        calendars = svc.list_calendars()
        if len(calendars) == 1:
            calendar_uuid = calendars[0]["uuid"]
        elif len(calendars) == 0:
            raise CommandValidationError("No calendars configured.", "Add one with: !calendar account add <url>")
        else:
            raise CommandValidationError(
                "Multiple calendars. Specify one with --calendar <uuid>.",
                "Usage: !calendar event import ics <path> --calendar <uuid>",
            )

    # ── Import from email attachment ───────────────────────────────────
    if remaining[0] == "from-email":
        if len(remaining) < 2:
            raise CommandValidationError(
                "Missing message UUID.",
                "Usage: !calendar event import ics from-email <msg-uuid>",
            )
        msg_uuid = remaining[1]
        from lighterbird.server.deps import get_email_service
        email_svc = get_email_service()
        ics_blobs = email_svc.messages.extract_ics_attachments(msg_uuid)
        if not ics_blobs:
            raise CommandValidationError(
                f"No .ics attachments found in message {msg_uuid[:8]}.",
            )
        uuids = []
        from lighterbird.calendar.ics import insert_ics_events
        for blob in ics_blobs:
            added = insert_ics_events(svc.db, calendar_uuid, blob.decode("utf-8", errors="replace"))
            uuids.extend(added)
        return {
            "type": "status",
            "title": "ICS Import from Email",
            "data": {"imported": len(uuids), "uuids": uuids, "source": "email"},
        }

    # ── Import from file ───────────────────────────────────────────────
    path = remaining[0]
    try:
        uuids = svc.import_ics(calendar_uuid, path)
    except FileNotFoundError:
        raise CommandValidationError(f"File not found: {path}")
    except Exception as e:
        raise CommandValidationError(str(e))
    return {"type": "status", "title": "ICS Import", "data": {"imported": len(uuids), "uuids": uuids}}


@command("calendar.sync-status", permission_level=PermissionLevel.READ)
def calendar_sync_status(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar sync-status [--all]

    Shows pending/retrying/failed sync jobs from the CalDAV sync queue.
    Use ``--all`` to show completed jobs too.
    """
    svc = get_calendar_service()
    if "all" in flags:
        jobs = list(svc.events.db.execute(
            "SELECT * FROM calendar_sync_queue ORDER BY id DESC LIMIT 100"
        ))
    else:
        jobs = list(svc.events.db.execute(
            "SELECT * FROM calendar_sync_queue WHERE status IN ('pending','running','failed') ORDER BY id DESC"
        ))
    return {"type": "status", "title": "Calendar Sync Queue", "data": {"jobs": jobs, "count": len(jobs)}}


@command("calendar.event.rrule")
def event_rrule_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event rrule — Show recurrence subcommands."""
    return {
        "type": "status",
        "title": "Event RRULE Commands",
        "data": {
            "_summary": (
                "Available !calendar event rrule commands:\n"
                "  !calendar event rrule set <uuid> <rrule>     — Set recurrence rule\n"
                "  !calendar event rrule clear <uuid>           — Remove recurrence\n"
                "  !calendar event rrule show <uuid>            — Show recurrence info\n"
                "\nExamples:\n"
                "  !calendar event rrule set <uuid> FREQ=WEEKLY;BYDAY=MO,WE,FR\n"
                "  !calendar event rrule set <uuid> FREQ=MONTHLY;BYDAY=1MO\n"
                "  !calendar event rrule set <uuid> FREQ=DAILY;COUNT=10"
            ),
        },
    }


@command("calendar.event.rrule.set",
         params=[{"name": "uuid", "type": "string", "help": "Event UUID", "required": True, "uuidSource": "calendar.events"},
                 {"name": "rrule", "type": "string", "help": "RRULE string (e.g. FREQ=WEEKLY;BYDAY=MO)", "required": True}])
def event_rrule_set(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event rrule set <uuid> <rrule>

    Set or change the recurrence rule on an existing event.
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing event UUID or RRULE.",
            "Usage: !calendar event rrule set <uuid> FREQ=WEEKLY;BYDAY=MO",
        )
    from lighterbird.calendar.rrule import parse_rrule

    uuid = remaining[0]
    rrule_str = remaining[1]
    try:
        rrule_str = parse_rrule(rrule_str) or ""
    except ValueError as e:
        raise CommandValidationError(str(e))
    svc: CalendarService = get_calendar_service()
    evt = svc.get_event(uuid)
    if not evt:
        raise CommandValidationError(f"Event not found: {uuid[:8]}")
    svc.events.update(uuid, {"rrule": rrule_str})
    return {"type": "status", "title": "RRULE Set", "data": {"uuid": uuid[:8], "rrule": rrule_str}}


@command("calendar.event.rrule.clear",
         params=[{"name": "uuid", "type": "string", "help": "Event UUID", "required": True, "uuidSource": "calendar.events"}])
def event_rrule_clear(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event rrule clear <uuid> — Remove recurrence from an event."""
    if not remaining:
        raise CommandValidationError(
            "Missing event UUID.",
            "Usage: !calendar event rrule clear <uuid>",
        )
    uuid = remaining[0]
    svc: CalendarService = get_calendar_service()
    evt = svc.get_event(uuid)
    if not evt:
        raise CommandValidationError(f"Event not found: {uuid[:8]}")
    svc.events.update(uuid, {"rrule": ""})
    return {"type": "status", "title": "RRULE Cleared", "data": {"uuid": uuid[:8]}}


@command("calendar.event.rrule.show", permission_level=PermissionLevel.READ,
         params=[{"name": "uuid", "type": "string", "help": "Event UUID", "required": True, "uuidSource": "calendar.events"}])
def event_rrule_show(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event rrule show <uuid> [--limit N]

    Show a recurring event with the next N occurrences expanded.
    Default limit is 10.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing event UUID.",
            "Usage: !calendar event rrule show <uuid>",
        )
    uuid = remaining[0]
    svc: CalendarService = get_calendar_service()
    evt = svc.get_event(uuid)
    if not evt:
        raise CommandValidationError(f"Event not found: {uuid[:8]}")
    rrule_str = (evt.get("rrule") or "").strip()
    if not rrule_str:
        return {"type": "status", "title": "No Recurrence", "data": {"uuid": uuid[:8], "rrule": "(none)"}}

    from lighterbird.calendar.rrule import expand_recurrences

    limit = int(flags.get("limit", 10))
    # Expand from today onward
    from datetime import UTC, datetime

    today = datetime.now(UTC).isoformat()
    far = datetime(2099, 12, 31, tzinfo=UTC).isoformat()
    instances = expand_recurrences(dict(evt), today, far, max_instances=limit)
    return {
        "type": "status",
        "title": f"Recurrence: {rrule_str}",
        "data": {
            "master": evt,
            "rrule": rrule_str,
            "next_occurrences": [
                {"start": i["start"], "end": i["end"]}
                for i in instances[1:]  # skip the master itself
            ],
            "count": len(instances) - 1,
        },
    }


@command("calendar.event.search", permission_level=PermissionLevel.READ)
def event_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar event search [--query TEXT] [--start DATE] [--end DATE] [--calendar UUID]"""
    svc: CalendarService = get_calendar_service()
    query = flags.get("query", " ".join(remaining) if remaining else "")
    start = flags.get("start", "2000-01-01")
    end = flags.get("end", "2099-12-31")
    calendar_uuid = flags.get("calendar")

    events = [dict(e) for e in svc.list_events(start, end, calendar_uuid=calendar_uuid)]
    if query:
        q = query.lower()
        events = [
            e for e in events
            if q in (e.get("title") or "").lower()
            or q in (e.get("description") or "").lower()
        ]
    return {"type": "calendar-events", "title": "Search Results", "data": {"events": events}}


# ── Calendar account sub-commands ───────────────────────────────────────


@command("calendar.account.list", permission_level=PermissionLevel.READ)
def cal_account_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar account list"""
    svc: CalendarService = get_calendar_service()
    calendars = [dict(c) for c in svc.list_calendars()]
    return {"type": "status", "title": "Calendars", "data": {"calendars": calendars}}


@command("calendar.account.add", interactive=True)
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


@command("calendar.account.modify", interactive=True,
         params=[{"name": "uuid", "type": "string", "help": "Calendar UUID", "required": True, "uuidSource": "calendar.accounts"}])
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


@command("calendar.account.delete", permission_level=PermissionLevel.DESTRUCTIVE, interactive=True,
         params=[{"name": "uuid", "type": "string", "help": "Calendar UUID(s)", "required": True, "uuidSource": "calendar.accounts", "repeatable": True}])
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
