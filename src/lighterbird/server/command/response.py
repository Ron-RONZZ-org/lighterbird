"""Response normalization helpers (legacy).

All database columns now use English names, matching the keys the
frontend expects. These pass-through functions exist only for
backward compatibility during the migration — they will be removed
in a future cleanup pass.

New code should use the raw dict keys directly.
"""

from __future__ import annotations

from typing import Any


def normalize_todo(todo: dict[str, Any]) -> dict[str, Any]:
    """Passthrough — DB columns are already in English."""
    result = dict(todo)
    # Rename DB columns that still use old names in raw responses
    # but have already been normalized in REST responses
    result.pop("_computed_priority", None)
    if "children" in result:
        result["children"] = [normalize_todo(c) for c in result["children"]]
    return result


def normalize_todo_for_db(todo: dict[str, Any]) -> dict[str, Any]:
    """Convert frontend-facing keys back to DB column names (legacy).

    Used only by command handlers that construct raw INSERT dicts.
    Will be removed once handlers are updated.
    """
    return todo


def normalize_account(acct: dict[str, Any]) -> dict[str, Any]:
    return dict(acct)


def normalize_message(msg: dict[str, Any]) -> dict[str, Any]:
    return dict(msg)


def normalize_calendar(cal: dict[str, Any]) -> dict[str, Any]:
    return dict(cal)


def normalize_event(evt: dict[str, Any]) -> dict[str, Any]:
    return dict(evt)


def normalize_contact(contact: dict[str, Any]) -> dict[str, Any]:
    return dict(contact)


def normalize_journal_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return dict(entry)
