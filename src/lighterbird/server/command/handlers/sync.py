"""Command handler for ``!sync`` — multi-module sync orchestration."""

from __future__ import annotations

import os
from typing import Any

from lighterbird.server.command.registry import command
from lighterbird.server.deps import (
    get_email_service,
    get_calendar_service,
    get_todo_service,
)
from lighterbird.server.command.errors import CommandValidationError


@command("sync")
def sync_cmd(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!sync [--email [account_email]] [--calendar] [--todo-attachments] [--all]

    Syncs email, calendar, and/or todo attachment data.
    Use ``--email`` to sync all email accounts, or specify an
    account email to sync a single account: ``--email user@example.com``.
    """
    email_flag = flags.get("email", "")
    calendar_flag = "calendar" in flags
    todo_attach_flag = "todo-attachments" in flags
    sync_all = "all" in flags
    force = "complete" in flags

    results: dict[str, Any] = {}
    if email_flag or sync_all:
        email_svc = get_email_service()
        if email_flag and email_flag != "true":
            sr = email_svc.sync_account(email_flag)
            results["email"] = sr.to_dict()
        else:
            email_results = email_svc.sync_all()
            total = sum(r.get("new", 0) for r in email_results.values())
            errors = []
            for r in email_results.values():
                errors.extend(r.get("errors", []))
            results["email"] = {"total": total, "new": total, "errors": errors}

    if calendar_flag or sync_all:
        cal_svc = get_calendar_service()
        cal_results = cal_svc.sync_all_calendars()
        results["calendar"] = cal_results

    if todo_attach_flag or sync_all:
        attach_results = _sync_todo_attachments(force=force)
        results["todo_attachments"] = attach_results

    return {"type": "status", "title": "Sync Results", "data": results}


def _sync_todo_attachments(force: bool = False) -> dict[str, Any]:
    """Re-sync todo file attachments from their original sources."""
    import hashlib

    svc = get_todo_service()
    attachments = svc.get_attachments_needing_sync()
    synced = 0
    errors: list[str] = []
    skipped_large: list[str] = []

    for att in attachments:
        source = att.get("original_path", "")
        todo_uuid = att.get("todo_uuid", "")
        att_uuid = att.get("uuid", "")

        if not source:
            continue

        # Check if it's a URL
        if source.startswith("http://") or source.startswith("https://"):
            try:
                import httpx
                resp = httpx.get(source, follow_redirects=True, timeout=30)
                resp.raise_for_status()
                content = resp.content
                size = len(content)

                # Size check
                if size > 5 * 1024 * 1024 and not force:
                    skipped_large.append(
                        f"{att.get('original_name', 'file')} "
                        f"({size / 1024 / 1024:.1f} MB)",
                    )
                    continue

                md5 = hashlib.md5(content).hexdigest()
                # Update attachment record
                svc.mark_attachment_synced(att_uuid, md5_checksum=md5)
                svc.update(todo_uuid, {})  # Touch updated_at
                synced += 1
            except Exception as e:
                errors.append(
                    f"{source[:60]}: {e}",
                )
        elif os.path.exists(source):
            # Local file — just verify it exists and compute md5
            try:
                md5 = hashlib.md5()
                with open(source, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        md5.update(chunk)
                size = os.path.getsize(source)
                svc.mark_attachment_synced(att_uuid, md5_checksum=md5.hexdigest())
                synced += 1
            except Exception as e:
                errors.append(f"{source}: {e}")
        else:
            errors.append(f"Source not found: {source}")

    result: dict[str, Any] = {"synced": synced}
    if errors:
        result["errors"] = errors
    if skipped_large:
        result["skipped_large"] = skipped_large
        result["note"] = (
            "Use --complete to force sync of large files."
        )
    return result
