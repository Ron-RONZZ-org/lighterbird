"""Command handlers for the ``!journal`` domain.

Registered paths:
    - journal.list
    - journal.write
    - journal.view
    - journal.search
"""

from __future__ import annotations

from datetime import date
from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.command.response import normalize_journal_entry
from lighterbird.server.deps import get_journal_service
from lighterbird.journal.services import JournalService


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
                "  !journal search       — Search journal entries"
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
        entries = [normalize_journal_entry(e) for e in svc.list_by_date(date_str)]
    else:
        entries = [normalize_journal_entry(e) for e in svc.list(limit=limit)]
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
    data = {"title": title, "text": text, "dato": date_str}
    entry = svc.create(data)
    return {"type": "status", "title": "Journal Entry Written", "data": {"uuid": entry["uuid"], "title": title}}


@command("journal.view")
def journal_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!journal view <uuid>"""
    if not remaining:
        raise CommandValidationError("Missing entry UUID.", "Usage: !journal view <uuid>")
    svc: JournalService = get_journal_service()
    entry = svc.get(remaining[0])
    if not entry:
        raise CommandValidationError(f"Journal entry not found: {remaining[0][:8]}")
    return {"type": "status", "title": entry.get("title", "(untitled)"), "data": normalize_journal_entry(entry)}


@command("journal.search")
def journal_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!journal search <query>"""
    svc: JournalService = get_journal_service()
    query = " ".join(remaining) if remaining else flags.get("query", "")
    entries = [normalize_journal_entry(e) for e in svc.search(query)]
    return {"type": "journal-list", "title": "Journal Search", "data": {"entries": entries, "total": len(entries)}}
