"""Command handler for ``!sync`` — multi-module sync orchestration."""

from __future__ import annotations

import os
from typing import Any

from lighterbird.server.command.registry import command
from lighterbird.server.deps import (
    get_calendar_service,
    get_email_service,
    get_todo_service,
)


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

    summary_parts: list[str] = []

    if email_flag or sync_all:
        email_svc = get_email_service()
        if email_flag and email_flag != "true":
            sr = email_svc.sync_account(email_flag)
            result = sr.to_dict()
            new_count = result.get("new", 0)
            errs = result.get("errors", [])
            summary_parts.append(f"Email ({email_flag}): {new_count} new")
            if errs:
                summary_parts.append(f"{len(errs)} error(s)")
        else:
            email_results = email_svc.sync_all()
            total_new = sum(r.get("new", 0) for r in email_results.values())
            total_errors = sum(len(r.get("errors", [])) for r in email_results.values())
            summary_parts.append(f"Email: {total_new} new")
            if total_errors:
                summary_parts.append(f"{total_errors} error(s)")

    if calendar_flag or sync_all:
        cal_svc = get_calendar_service()
        cal_results = cal_svc.sync_all_calendars()
        cal_new = sum(r.get("new", 0) for r in cal_results.values())
        cal_errs = sum(len(r.get("errors", [])) for r in cal_results.values())
        summary_parts.append(f"Calendar: {cal_new} synced")
        if cal_errs:
            summary_parts.append(f"{cal_errs} error(s)")

    if todo_attach_flag or sync_all:
        attach_results = _sync_todo_attachments(force=force)
        synced = attach_results.get("synced", 0)
        attach_errs = attach_results.get("errors", [])
        summary_parts.append(f"Attachments: {synced} synced")
        if attach_errs:
            summary_parts.append(f"{len(attach_errs)} error(s)")

    message = " — ".join(summary_parts) if summary_parts else "Nothing to sync."

    return {"type": "status", "title": "Sync Complete", "data": {"message": message}}


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
