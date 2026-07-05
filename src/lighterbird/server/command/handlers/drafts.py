"""Command handlers for the ``!{domain} draft`` commands.

Registered paths:

    email.draft          — List / recall email drafts
    journal.draft        — List / recall journal drafts
    todo.draft           — List / recall todo drafts
    calendar.draft       — List / recall calendar event drafts
    letter.draft         — List / recall letter drafts
"""

from __future__ import annotations

from typing import Any

from lighterbird.core.drafts import get_draft, list_drafts
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command

DOMAIN_MAP = {
    "email": "email",
    "journal": "journal",
    "todo": "todo",
    "calendar": "calendar-event",
    "letter": "letter",
}

DOMAIN_LABELS = {
    "email": "Email",
    "journal": "Journal",
    "todo": "Todo",
    "calendar": "Calendar Event",
    "letter": "Letter",
}


def _format_drafts(drafts: list[dict[str, Any]], domain_label: str) -> list[dict[str, str]]:
    entries = []
    for d in drafts:
        title = d.get("title", "(untitled)")
        updated = d.get("updated_at", "")[:16].replace("T", " ")
        entries.append({
            "uuid": d["uuid"],
            "title": title,
            "updated": updated,
            "domain": d.get("domain", ""),
        })
    return entries


def _handle_draft_list(domain: str, remaining: list[str]) -> dict[str, Any]:
    """Handle !{domain} draft [<uuid>] — list or recall a specific draft."""
    actual_domain = DOMAIN_MAP[domain]
    domain_label = DOMAIN_LABELS[domain]
    drafts = list_drafts(actual_domain)

    if not drafts:
        return {
            "type": "status",
            "title": f"{domain_label} Drafts",
            "data": {"message": f"No {domain_label.lower()} drafts found."},
        }

    return {
        "type": "status",
        "title": f"{domain_label} Drafts ({len(drafts)})",
        "data": {
            "_summary": f"{len(drafts)} {domain_label.lower()} draft(s) available.\n"
                        f"Use !{domain} draft <uuid> to recall a draft.",
            "drafts": _format_drafts(drafts, domain_label),
        },
    }


@command("email.draft")
def email_draft(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email draft [<uuid>]

    List saved email drafts or recall a specific draft by UUID.
    When recalled, opens the compose form with pre-filled data.
    """
    if remaining:
        uuid = remaining[0]
        draft = get_draft(uuid)
        if not draft:
            raise CommandValidationError(f"Draft not found: {uuid}")
        if draft.get("domain") != "email":
            raise CommandValidationError(f"Draft {uuid} is not an email draft.")
        return {
            "type": "form-required",
            "title": "Recall Draft: " + draft.get("title", "(untitled)"),
            "data": {
                "form": "email-send",
                "initialData": {
                    **draft.get("data", {}),
                    "_returnType": "email-list",
                    "_returnTitle": "Emails",
                    "_returnIdKey": "persistent-email-list",
                },
            },
        }
    return _handle_draft_list("email", remaining)


@command("journal.draft")
def journal_draft(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!journal draft [<uuid>]

    List saved journal drafts or recall a specific draft by UUID.
    """
    if remaining:
        uuid = remaining[0]
        draft = get_draft(uuid)
        if not draft:
            raise CommandValidationError(f"Draft not found: {uuid}")
        if draft.get("domain") != "journal":
            raise CommandValidationError(f"Draft {uuid} is not a journal draft.")
        return {
            "type": "form-required",
            "title": "Recall Draft: " + draft.get("title", "(untitled)"),
            "data": {
                "form": "journal-write",
                "initialData": {
                    **draft.get("data", {}),
                    "_returnType": "journal-list",
                    "_returnTitle": "Journal",
                    "_returnIdKey": "persistent-journal-list",
                },
            },
        }
    return _handle_draft_list("journal", remaining)


@command("todo.draft")
def todo_draft(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!todo draft [<uuid>]

    List saved todo drafts or recall a specific draft by UUID.
    """
    if remaining:
        uuid = remaining[0]
        draft = get_draft(uuid)
        if not draft:
            raise CommandValidationError(f"Draft not found: {uuid}")
        if draft.get("domain") != "todo":
            raise CommandValidationError(f"Draft {uuid} is not a todo draft.")
        return {
            "type": "form-required",
            "title": "Recall Draft: " + draft.get("title", "(untitled)"),
            "data": {
                "form": "todo-add",
                "initialData": {
                    **draft.get("data", {}),
                    "_returnType": "todo-list",
                    "_returnTitle": "Todos",
                    "_returnIdKey": "persistent-todo-list",
                },
            },
        }
    return _handle_draft_list("todo", remaining)


@command("calendar.draft")
def calendar_draft(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!calendar draft [<uuid>]

    List saved calendar event drafts or recall a specific draft by UUID.
    """
    if remaining:
        uuid = remaining[0]
        draft = get_draft(uuid)
        if not draft:
            raise CommandValidationError(f"Draft not found: {uuid}")
        if draft.get("domain") != "calendar-event":
            raise CommandValidationError(f"Draft {uuid} is not a calendar event draft.")
        return {
            "type": "form-required",
            "title": "Recall Draft: " + draft.get("title", "(untitled)"),
            "data": {
                "form": "calendar-event-add",
                "initialData": {
                    **draft.get("data", {}),
                    "_returnType": "calendar-events",
                    "_returnTitle": "Calendar Events",
                    "_returnIdKey": "persistent-calendar-events",
                },
            },
        }
    return _handle_draft_list("calendar", remaining)

@command("letter.draft")
def letter_draft(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter draft [<uuid>]

    List saved letter drafts or recall a specific draft by UUID.
    When recalled, opens the send form with pre-filled data.
    """
    if remaining:
        uuid = remaining[0]
        draft = get_draft(uuid)
        if not draft:
            raise CommandValidationError(f"Draft not found: {uuid}")
        if draft.get("domain") != "letter":
            raise CommandValidationError(f"Draft {uuid} is not a letter draft.")
        return {
            "type": "form-required",
            "title": "Recall Draft: " + draft.get("title", "(untitled)"),
            "data": {
                "form": "letter-send",
                "initialData": {
                    **draft.get("data", {}),
                    "_returnType": "letter-list",
                    "_returnTitle": "Letters",
                    "_returnIdKey": "persistent-letter-list",
                },
            },
        }
    return _handle_draft_list("letter", remaining)
