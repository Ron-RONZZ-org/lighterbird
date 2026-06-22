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
from lighterbird.server.deps import get_contact_service
from lighterbird.contacts.services import ContactService


@command("contacts.list")
def contacts_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contacts list [--limit N]"""
    svc: ContactService = get_contact_service()
    limit = int(flags.get("limit", 50))
    contacts = svc.list(limit=limit)
    return {"type": "status", "title": "Contacts", "data": {"contacts": contacts}}


@command("contacts.add")
def contacts_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contacts add <email> [name] [phone]"""
    if not remaining:
        raise CommandValidationError("Missing email.", "Usage: !contacts add <email> [name] [phone]")
    email = remaining[0]
    name = remaining[1] if len(remaining) > 1 else flags.get("name", "")
    phone = remaining[2] if len(remaining) > 2 else flags.get("phone", "")
    svc: ContactService = get_contact_service()
    data = {"retposto": email, "nomo": name, "telefonnumero": phone}
    contact = svc.create(data)
    return {"type": "status", "title": "Contact Added", "data": {"uuid": contact["uuid"], "email": email}}


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
    return {"type": "status", "title": contact.get("nomo", "(unnamed)"), "data": contact}


@command("contacts.modify")
def contacts_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contacts modify <uuid> [--name NAME] [--email EMAIL] [--phone PHONE] [--org ORG] [--notes NOTES]"""
    if not remaining:
        raise CommandValidationError("Missing contact UUID.", "Usage: !contacts modify <uuid> [--name ...]")
    uuid = remaining[0]
    svc: ContactService = get_contact_service()
    updates = {}
    field_map = {"name": "nomo", "email": "retposto", "phone": "telefonnumero", "org": "organizo", "notes": "notoj"}
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
    contacts = svc.search(query)
    return {"type": "status", "title": "Contact Search", "data": {"contacts": contacts}}
