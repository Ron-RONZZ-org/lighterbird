"""Command handlers for the ``!contact`` domain.

Registered paths:
    - contact.list
    - contact.add
    - contact.view
    - contact.modify
    - contact.delete
    - contact.search
    - contact.export.vcf
    - contact.import.vcf
"""

from __future__ import annotations

import json
from typing import Any

from lighterbird.contacts.services import ContactService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_contact_service


def _parse_custom_fields(raw: str) -> dict[str, str]:
    """Parse ``key:value`` pairs, comma-separated.

    ``--custom "key1:val1,key2:val2"`` → ``{"key1":"val1","key2":"val2"}``
    """
    result: dict[str, str] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            key, _, value = part.partition(":")
            result[key.strip()] = value.strip()
        else:
            result[part] = ""
    return result


def _parse_multi_flag(raw: str) -> list[dict[str, str]]:
    """Parse a comma-separated list of tag:value pairs.

    ``"work:a@b.com,home:c@d.com"`` -> ``[{"tag":"work","value":"a@b.com"}, ...]``
    If no colon, the whole string is the value with an empty tag.
    """
    items = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            tag, val = part.split(":", 1)
            items.append({"tag": tag.strip(), "value": val.strip()})
        else:
            items.append({"tag": "", "value": part})
    return items


@command("contact")
def contacts_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact — Show available contact subcommands."""
    return {
        "type": "status",
        "title": "Contact Commands",
        "data": {
            "_summary": (
                "Available !contact commands:\n"
                "  !contact list                                   — List contacts\n"
                "  !contact add --first-name GIVEN --last-name FAMILY  — Add a contact\n"
                "  !contact view <uuid>                            — View a contact\n"
                "  !contact modify <uuid>                          — Modify a contact\n"
                "  !contact delete <uuid> [uuid...]                — Delete a contact\n"
                "  !contact search <query>                         — Search contacts"
            ),
        },
    }


@command("contact.list")
def contact_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact list [--limit N]"""
    svc: ContactService = get_contact_service()
    limit = int(flags.get("limit", 50))
    contacts = [dict(c) for c in svc.list(limit=limit)]
    return {"type": "contacts-list", "title": "Contacts", "data": {"contacts": contacts}}


@command("contact.add")
def contact_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact add --first-name GIVEN --last-name FAMILY [--middle-names M]
    [--email tag:value,...] [--phone tag:value,...] [--organization ORG]
    [--notes NOTES] [--dob YYYY-MM-DD] [--place-of-birth PLACE]
    [--address ADDR] [--post-code CODE] [--position POS] [--custom key:val,...]
    """
    given_name = flags.get("first-name", "")
    family_name = flags.get("last-name", "")
    if not given_name and not family_name:
        raise CommandValidationError(
            "Missing contact name.",
            "Usage: !contact add --first-name GIVEN --last-name FAMILY "
            "[--email tag:value,...] [--phone tag:value,...] [--organization ORG] "
            "[--notes NOTES] [--middle-names M] [--dob YYYY-MM-DD] "
            "[--place-of-birth PLACE] [--address ADDR] [--post-code CODE] "
            "[--position POS] [--custom key:val,...]",
        )

    svc: ContactService = get_contact_service()
    data: dict[str, Any] = {
        "given_name": given_name,
        "family_name": family_name,
        "emails": json.dumps(_parse_multi_flag(flags.get("email", ""))),
        "phones": json.dumps(_parse_multi_flag(flags.get("phone", ""))),
        "organization": flags.get("organization", ""),
        "notes": flags.get("notes", ""),
    }

    for key, flag in (
        ("middle_names", "middle-names"),
        ("date_of_birth", "dob"),
        ("place_of_birth", "place-of-birth"),
        ("address", "address"),
        ("post_code", "post-code"),
        ("position", "position"),
    ):
        if flag in flags:
            data[key] = flags[flag]

    if "custom" in flags:
        data["custom_fields"] = json.dumps(_parse_custom_fields(flags["custom"]), ensure_ascii=False)

    display_name = " ".join(p for p in (given_name, flags.get("middle-names", ""), family_name) if p)
    contact = svc.create(data)
    return {"type": "status", "title": "Contact Added", "data": {"uuid": contact["uuid"], "name": display_name}}


@command("contact.view")
def contact_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact view <uuid-or-email>"""
    if not remaining:
        raise CommandValidationError("Missing contact UUID or email.", "Usage: !contact view <uuid>")
    svc: ContactService = get_contact_service()
    identifier = remaining[0]
    contact = svc.get(identifier)
    if not contact and "@" in identifier:
        contact = svc.find_by_email(identifier)
    if not contact:
        raise CommandValidationError(f"Contact not found: {identifier[:16]}")
    return {"type": "status", "title": contact.get("given_name", "(unnamed)"), "data": dict(contact)}


@command("contact.modify")
def contact_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact modify <uuid> [--first-name GIVEN] [--last-name FAMILY]
    [--email tag:value,...] [--phone tag:value,...] [--organization ORG]
    [--notes NOTES] [--middle-names M] [--dob YYYY-MM-DD]
    [--place-of-birth PLACE] [--address ADDR] [--post-code CODE]
    [--position POS] [--custom key:val,...]
    """
    if not remaining:
        raise CommandValidationError("Missing contact UUID.", "Usage: !contact modify <uuid> [--first-name ...]")
    uuid = remaining[0]
    svc: ContactService = get_contact_service()
    updates: dict[str, Any] = {}
    field_map: dict[str, str] = {
        "first-name": "given_name",
        "last-name": "family_name",
        "organization": "organization",
        "notes": "notes",
        "middle-names": "middle_names",
        "dob": "date_of_birth",
        "place-of-birth": "place_of_birth",
        "address": "address",
        "post-code": "post_code",
        "position": "position",
    }
    for flag_key, db_key in field_map.items():
        if flag_key in flags:
            updates[db_key] = flags[flag_key]

    if "email" in flags:
        updates["emails"] = json.dumps(_parse_multi_flag(flags["email"]))
    if "phone" in flags:
        updates["phones"] = json.dumps(_parse_multi_flag(flags["phone"]))
    if "custom" in flags:
        updates["custom_fields"] = json.dumps(_parse_custom_fields(flags["custom"]), ensure_ascii=False)

    if not updates:
        raise CommandValidationError("No fields to modify.", "Usage: !contact modify <uuid> [--first-name ...] [--email ...] ...")
    svc.update(uuid, updates)
    return {"type": "status", "title": "Contact Modified", "data": {"uuid": uuid[:8]}}


@command("contact.delete")
def contact_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact delete <uuid> [uuid...]"""
    if not remaining:
        raise CommandValidationError("Missing contact UUID(s).", "Usage: !contact delete <uuid> [uuid...]")
    svc: ContactService = get_contact_service()
    removed = []
    for uuid in remaining:
        try:
            svc.delete(uuid)
            removed.append(uuid[:8])
        except Exception:
            pass
    return {"type": "status", "title": "Contact(s) Deleted", "data": {"removed": removed}}


@command("contact.search")
def contact_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact search <query>"""
    svc: ContactService = get_contact_service()
    query = " ".join(remaining) if remaining else flags.get("query", "")
    contacts = [dict(c) for c in svc.search(query)]
    return {"type": "contacts-list", "title": "Contact Search", "data": {"contacts": contacts}}


@command("contact.export.vcf")
def contact_export_vcf(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact export vcf <uuid> [--all]"""
    svc: ContactService = get_contact_service()
    if "all" in flags:
        vcf_text = svc.export_vcf(uuid=None)
        return {"type": "status", "title": "VCF Export", "data": {"vcf": vcf_text}}
    if not remaining:
        raise CommandValidationError(
            "Missing contact UUID or --all flag.",
            "Usage: !contact export vcf <uuid> or !contact export vcf --all",
        )
    vcf_text = svc.export_vcf(uuid=remaining[0])
    return {"type": "status", "title": "VCF Export", "data": {"vcf": vcf_text}}


@command("contact.import.vcf")
def contact_import_vcf(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact import vcf <path>"""
    if not remaining:
        raise CommandValidationError(
            "Missing VCF file path.",
            "Usage: !contact import vcf <path/to/file.vcf>",
        )
    svc: ContactService = get_contact_service()
    count = svc.import_vcf(remaining[0])
    return {"type": "status", "title": "VCF Import", "data": {"imported": count}}
