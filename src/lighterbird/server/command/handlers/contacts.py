"""Command handlers for the ``!contacts`` domain.

Registered paths:
    - contacts.list
    - contacts.add
    - contacts.view
    - contacts.modify
    - contacts.remove
    - contacts.search
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.command.response import normalize_contact
from lighterbird.server.deps import get_contact_service
from lighterbird.contacts.services import ContactService


@command("contacts.list")
def contacts_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contacts list [--limit N]"""
    svc: ContactService = get_contact_service()
    limit = int(flags.get("limit", 50))
    contacts = [normalize_contact(c) for c in svc.list(limit=limit)]
    return {"type": "status", "title": "Contacts", "data": {"contacts": contacts}}


@command("contacts.add")
def contacts_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contacts add <name> [--email EMAIL] [--phone PHONE] [--org ORG] [--notes NOTES]

    Name is the only required positional argument.
    All other details are optional flags.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing contact name.",
            "Usage: !contacts add \"Full Name\" [--email email@example.com] [--phone NUMBER] [--org ORG] [--notes NOTES]",
        )
    name = remaining[0]
    email = flags.get("email", "")
    phone = flags.get("phone", "")
    org = flags.get("org", "")
    notes = flags.get("notes", "")

    svc: ContactService = get_contact_service()
    data = {
        "nomo": name,
        "retposto": email,
        "telefonnumero": phone,
        "organizo": org,
        "notoj": notes,
    }
    contact = svc.create(data)
    return {"type": "status", "title": "Contact Added", "data": {"uuid": contact["uuid"], "name": name}}


@command("contacts.view")
def contacts_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contacts view <uuid-or-email>"""
    if not remaining:
        raise CommandValidationError("Missing contact UUID or email.", "Usage: !contacts view <uuid>")
    svc: ContactService = get_contact_service()
    identifier = remaining[0]
    contact = svc.get(identifier)
    if not contact and "@" in identifier:
        contact = svc.find_by_email(identifier)
    if not contact:
        raise CommandValidationError(f"Contact not found: {identifier[:16]}")
    return {"type": "status", "title": contact.get("nomo", "(unnamed)"), "data": normalize_contact(contact)}


@command("contacts.modify")
def contacts_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contacts modify <uuid> [--name NAME] [--email EMAIL] [--phone PHONE] [--org ORG] [--notes NOTES]"""
    if not remaining:
        raise CommandValidationError("Missing contact UUID.", "Usage: !contacts modify <uuid> [--name ...]")
    uuid = remaining[0]
    svc: ContactService = get_contact_service()
    updates = {}
    field_map = {"name": "nomo", "email": "retposto", "phone": "telefonnumero", "organization": "organizo", "org": "organizo", "notes": "notoj"}
    for flag_key, db_key in field_map.items():
        if flag_key in flags:
            updates[db_key] = flags[flag_key]
    if not updates:
        raise CommandValidationError("No fields to modify.", "Usage: !contacts modify <uuid> [--name NAME] [--email EMAIL] ...")
    svc.update(uuid, updates)
    return {"type": "status", "title": "Contact Modified", "data": {"uuid": uuid[:8]}}


@command("contacts.remove")
def contacts_remove(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contacts remove <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError("Missing contact UUID(s).", "Usage: !contacts remove <uuid> [uuid...]")
    svc: ContactService = get_contact_service()
    removed = []
    for uuid in remaining:
        try:
            svc.delete(uuid)
            removed.append(uuid[:8])
        except Exception:
            pass
    return {"type": "status", "title": "Contact(s) Removed", "data": {"removed": removed}}


@command("contacts.search")
def contacts_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contacts search <query>"""
    svc: ContactService = get_contact_service()
    query = " ".join(remaining) if remaining else flags.get("query", "")
    contacts = [normalize_contact(c) for c in svc.search(query)]
    return {"type": "status", "title": "Contact Search", "data": {"contacts": contacts}}