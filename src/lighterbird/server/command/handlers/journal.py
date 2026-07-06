"""Command handlers for the ``!journal`` domain.

Registered paths:
    - journal.list
    - journal.write
    - journal.view
    - journal.search
    - journal.delete
"""

from __future__ import annotations

from datetime import date
from typing import Any

from lighterbird.journal.services import JournalService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.helpers import require_found, require_uuid
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_journal_service


@command("journal")
def journal_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!journal — Show available journal subcommands."""
    return {
        "type": "status",
        "title": "Journal Commands",
        "data": {
            "_summary": (
                "Available !journal commands:\n"
                "  !journal list         — List journal entries\n"
                "  !journal write        — Write a journal entry\n"
                "  !journal view         — View a journal entry\n"
                "  !journal search       — Search journal entries\n"
                "  !journal delete       — Delete journal entry(s)\n"
                "  !journal draft        — List / recall journal drafts\n"
                "  !journal export md    — Export entry(s) as .md\n"
                "  !journal import md    — Import entry(s) from .md"
            ),
        },
    }


@command("journal.list")
def journal_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!journal list [--date YYYY-MM-DD] [--limit N]"""
    svc: JournalService = get_journal_service()
    date_str = flags.get("date")
    limit = int(flags.get("limit", 50))
    if date_str:
        entries = [dict(e) for e in svc.list_by_date(date_str)]
    else:
        entries = [dict(e) for e in svc.list(limit=limit)]
    return {"type": "journal-list", "title": "Journal", "data": {"entries": entries, "total": len(entries)}}


@command("journal.write")
def journal_write(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!journal write <title> [--date YYYY-MM-DD] [--text CONTENT]

    Writes a journal entry. The text content can be provided via --text
    or as remaining tokens after the title.
    """
    if not remaining:
        raise CommandValidationError("Missing journal entry title.", "Usage: !journal write <title> [--date ...] [--text ...]")
    title = remaining[0]
    text = flags.get("text", " ".join(remaining[1:]) if len(remaining) > 1 else "")
    date_str = flags.get("date", date.today().isoformat())
    svc: JournalService = get_journal_service()
    data = {"title": title, "text": text, "date": date_str}
    entry = svc.create(data)
    return {"type": "status", "title": "Journal Entry Written", "data": {"uuid": entry["uuid"], "title": title}}


@command("journal.view")
def journal_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!journal view <uuid>"""
    uuid = require_uuid(remaining, "Usage: !journal view <uuid>")
    svc: JournalService = get_journal_service()
    entry = svc.get(uuid)
    require_found(entry, uuid[:8], "journal entry")
    return {"type": "status", "title": entry.get("title", "(untitled)"), "data": dict(entry)}


@command("journal.search")
def journal_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!journal search <query>"""
    svc: JournalService = get_journal_service()
    query = " ".join(remaining) if remaining else flags.get("query", "")
    entries = [dict(e) for e in svc.search(query)]
    return {"type": "journal-list", "title": "Journal Search", "data": {"entries": entries, "total": len(entries)}}


@command("journal.delete")
def journal_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!journal delete <uuid> [uuid...] — Delete one or more journal entries."""
    if not remaining:
        raise CommandValidationError(
            "Missing journal entry UUID(s).",
            "Usage: !journal delete <uuid> [uuid...]",
        )

    svc: JournalService = get_journal_service()
    removed: list[str] = []
    not_found: list[str] = []

    for raw in remaining:
        entry = svc.get(raw)
        if entry:
            svc.delete(raw)
            removed.append(raw[:8])
        else:
            not_found.append(raw[:8])

    return {
        "type": "status",
        "title": "Journal Entry(s) Deleted",
        "data": {"removed": removed, "not_found": not_found},
    }


@command("journal.export")
def journal_export(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!journal export md <uuid> [uuid...]"""
    if not remaining or remaining[0] != "md":
        raise CommandValidationError(
            "Missing subcommand.",
            "Usage: !journal export md <uuid> [uuid...]",
        )
    uuids = remaining[1:]
    if not uuids:
        raise CommandValidationError(
            "Missing entry UUID(s).",
            "Usage: !journal export md <uuid> [uuid...]",
        )
    svc: JournalService = get_journal_service()
    md = svc.export_md(uuids=uuids)
    return {"type": "markdown", "title": "Journal Export", "data": md}


@command("journal.import")
def journal_import(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!journal import md <path>"""
    if not remaining or remaining[0] != "md":
        raise CommandValidationError(
            "Missing subcommand.",
            "Usage: !journal import md <path>",
        )
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing file path.",
            "Usage: !journal import md <path>",
        )
    path = remaining[1]
    svc: JournalService = get_journal_service()
    try:
        uuids = svc.import_md(path)
    except FileNotFoundError:
        raise CommandValidationError(f"File not found: {path}")
    return {
        "type": "status",
        "title": "Journal Import",
        "data": {"imported": uuids, "count": len(uuids)},
    }
