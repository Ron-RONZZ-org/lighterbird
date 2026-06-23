"""Command handler for the ``!sync`` domain.

!sync [--email] [--calendar] [--account UUID] [--calendar-uuid UUID]

If no domain flags given, syncs both email and calendar.
Use --account to sync a specific email account.
Use --calendar-uuid to sync a specific calendar.
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service, get_calendar_service


@command("sync")
def sync_all(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!sync [--email] [--calendar] [--account UUID] [--calendar-uuid UUID]

    Synchronise data. Without domain flags, syncs all.
    Use --account to sync a specific email account.
    Use --calendar-uuid to sync a specific calendar.
    """
    email_svc = get_email_service()
    cal_svc = get_calendar_service()

    has_domain_flag = "email" in flags or "calendar" in flags
    do_email = "email" in flags or not has_domain_flag
    do_calendar = "calendar" in flags or not has_domain_flag

    results: dict[str, Any] = {}

    if do_email:
        if "account" in flags:
            # Sync specific email account
            acct_uuid = flags["account"]
            result = email_svc.sync_account(acct_uuid)
            results["email"] = result.to_dict()
        else:
            results["email"] = email_svc.sync_all()

    if do_calendar:
        if "calendar_uuid" in flags:
            # Sync specific calendar
            cal_uuid = flags["calendar_uuid"]
            result = cal_svc.sync_calendar(cal_uuid)
            results["calendar"] = result
        else:
            results["calendar"] = cal_svc.sync_all_calendars()

    return {"type": "status", "title": "Sync Complete", "data": results}
