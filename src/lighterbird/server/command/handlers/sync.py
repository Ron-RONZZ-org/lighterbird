"""Command handler for ``!sync`` — multi-module sync orchestration."""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service, get_calendar_service


@command("sync")
def sync_cmd(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!sync [--email [account_email]] [--calendar] [--all]

    Syncs email and/or calendar data from remote servers.
    Use ``--email`` to sync all email accounts, or specify an
    account email to sync a single account: ``--email user@example.com``.
    """
    # Only sync if explicitly told to (avoid accidental server hits)
    from lighterbird.email.imap.sync import SyncResult

    email_flag = flags.get("email", "")
    calendar_flag = "calendar" in flags
    sync_all = "all" in flags

    results: dict[str, Any] = {}
    if email_flag or sync_all:
        email_svc = get_email_service()
        if email_flag and email_flag != "true":
            # Sync specific account
            sr = email_svc.sync_account(email_flag)
            results["email"] = sr.to_dict()
        else:
            # Sync all accounts
            email_results = email_svc.sync_all()
            total = sum(r.get("new", 0) for r in email_results.values())
            errors = []
            for r in email_results.values():
                errors.extend(r.get("errors", []))
            results["email"] = {"total": total, "new": total, "errors": errors}

    if calendar_flag or sync_all:
        cal_svc = get_calendar_service()
        cal_results = cal_svc.sync_all()
        results["calendar"] = cal_results

    return {"type": "status", "title": "Sync Results", "data": results}
