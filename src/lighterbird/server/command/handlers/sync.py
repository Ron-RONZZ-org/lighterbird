"""Command handler for the ``!sync`` domain.

!sync [--email] [--calendar]

If no flags given, syncs both email and calendar.
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service, get_calendar_service


@command("sync")
def sync_all(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!sync [--email] [--calendar]

    Synchronise data. Without flags, syncs all.
    """
    email_svc = get_email_service()
    cal_svc = get_calendar_service()

    do_email = flags.get("email", "true") if not flags else flags.get("email", "false")
    do_calendar = flags.get("calendar", "true") if not flags else flags.get("calendar", "false")

    # If no flags at all, sync all
    if not flags:
        do_email = "true"
        do_calendar = "true"

    # Resolve boolean strings
    sync_email = do_email.lower() in ("true", "1", "yes")
    sync_cal = do_calendar.lower() in ("true", "1", "yes")

    results: dict[str, Any] = {}
    if sync_email:
        results["email"] = email_svc.sync_all()
    if sync_cal:
        results["calendar"] = cal_svc.sync_all_calendars()
    return {"type": "status", "title": "Sync Complete", "data": results}
