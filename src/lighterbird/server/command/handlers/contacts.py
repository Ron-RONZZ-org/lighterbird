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
import logging
from typing import Any

from lightercore.permissions import PermissionLevel

from lighterbird.contacts.services import ContactService
from lighterbird.core.paths import safe_resolve_path
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_contact_service

logger = logging.getLogger(__name__)


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


@command("contact.list", permission_level=PermissionLevel.READ)
def contact_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact list [--limit N]"""
    svc: ContactService = get_contact_service()
    limit = int(flags.get("limit", 50))
    contacts = [dict(c) for c in svc.list(limit=limit)]
    return {"type": "contacts-list", "title": "Contacts", "data": {"contacts": contacts}}


@command("contact.add",
         params=[],
         flags=[
             {"name": "first-name", "type": "string", "help": "Given name", "required": False, "width": "short"},
             {"name": "last-name", "type": "string", "help": "Family name", "required": False, "width": "short"},
             {"name": "email", "type": "string", "help": "tag:value,... email addresses"},
             {"name": "phone", "type": "string", "help": "tag:value,... phone numbers"},
             {"name": "organization", "type": "string", "help": "Organization", "autocompleteSource": "contact/org"},
             {"name": "notes", "type": "string", "help": "Notes"},
             {"name": "middle-names", "type": "string", "help": "Middle names", "width": "short"},
             {"name": "dob", "type": "date", "help": "Date of birth (YYYY-MM-DD)", "width": "short"},
             {"name": "place-of-birth", "type": "string", "help": "Place of birth"},
             {"name": "address", "type": "string", "help": "Street address"},
             {"name": "post-code", "type": "string", "help": "Postal code", "width": "short"},
             {"name": "position", "type": "string", "help": "Job position", "width": "medium"},
         ],
         interactive=True,
         form_type="contacts-add",
)
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


@command("contact.view", permission_level=PermissionLevel.READ)
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


@command("contact.modify", interactive=True, form_type="contacts-modify")
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
    return {"type": "status", "title": "Contact Modified", "data": {"uuid": uuid}}


@command("contact.delete", permission_level=PermissionLevel.DESTRUCTIVE)
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
            logger.warning("Failed to delete contact %s", uuid[:8])
    return {"type": "status", "title": "Contact(s) Deleted", "data": {"removed": removed}}


@command("contact.search", permission_level=PermissionLevel.READ)
def contact_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact search <query>"""
    svc: ContactService = get_contact_service()
    query = " ".join(remaining) if remaining else flags.get("query", "")
    contacts = [dict(c) for c in svc.search(query)]
    return {"type": "contacts-list", "title": "Contact Search", "data": {"contacts": contacts}}


@command("contact.export.vcf", permission_level=PermissionLevel.READ)
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


@command("contact.clean", permission_level=PermissionLevel.DESTRUCTIVE)
def contact_clean(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact clean — Find and report duplicate contacts.

    Scans all contacts for duplicates by email address and name+org.
    Returns groups of potential duplicates for review.
    Use ``!contact merge <keep-uuid> <remove-uuid>...`` to merge.
    """
    svc: ContactService = get_contact_service()
    groups = svc.find_duplicates()
    if not groups:
        return {"type": "status", "title": "No Duplicates Found", "data": {"groups": []}}
    return {
        "type": "status",
        "title": f"Found {len(groups)} Duplicate Group(s)",
        "data": {"groups": groups, "count": len(groups)},
    }


@command("contact.merge", permission_level=PermissionLevel.DESTRUCTIVE)
def contact_merge(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact merge <keep-uuid> <remove-uuid> [remove-uuid...]

    Merges duplicate contacts into one. The first UUID is kept; the
    rest are merged into it and then deleted.
    Emails, phones, and notes are consolidated.
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing UUIDs.",
            "Usage: !contact merge <keep-uuid> <remove-uuid> [remove-uuid...]",
        )
    keep_uuid = remaining[0]
    remove_uuids = remaining[1:]
    svc: ContactService = get_contact_service()
    try:
        result = svc.merge_duplicates(keep_uuid, remove_uuids)
    except ValueError as e:
        raise CommandValidationError(str(e))
    return {
        "type": "status",
        "title": "Contacts Merged",
        "data": {"kept": keep_uuid[:8], "merged": len(remove_uuids), "updated": result},
    }


@command("contact.import.vcf")
def contact_import_vcf(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact import vcf <path>"""
    if not remaining:
        raise CommandValidationError(
            "Missing VCF file path.",
            "Usage: !contact import vcf <path/to/file.vcf>",
        )
    try:
        safe_resolve_path(remaining[0])
    except (ValueError, FileNotFoundError, IsADirectoryError) as e:
        raise CommandValidationError(str(e))
    svc: ContactService = get_contact_service()
    count = svc.import_vcf(remaining[0])
    return {"type": "status", "title": "VCF Import", "data": {"imported": count}}


@command("contact.category")
def contact_category_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact category — Show category subcommands."""
    return {
        "type": "status",
        "title": "Contact Category Commands",
        "data": {
            "_summary": (
                "Available !contact category commands:\n"
                "  !contact category list [--all]      — List all known categories\n"
                "  !contact category set <uuid> <cat>   — Set category on a contact\n"
                "  !contact category add <uuid> <cat>   — Add category to a contact\n"
                "  !contact category remove <uuid> <cat> — Remove category from a contact"
            ),
        },
    }


@command("contact.category.list", permission_level=PermissionLevel.READ)
def contact_category_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact category list [--all]

    Lists categories. By default shows categories in use.
    Use ``--all`` to show all distinct category values.
    """
    svc: ContactService = get_contact_service()
    contacts = svc.list(limit=10000)
    all_cats: set[str] = set()
    for c in contacts:
        cat_str = (c.get("category") or "").strip()
        if cat_str:
            for cat in cat_str.split(","):
                cat = cat.strip()
                if cat:
                    all_cats.add(cat)
    sorted_cats = sorted(all_cats)
    return {"type": "status", "title": "Contact Categories", "data": {"categories": sorted_cats, "count": len(sorted_cats)}}


@command("contact.category.set")
def contact_category_set(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact category set <uuid> <category>

    Replaces all categories on a contact. Multiple categories: comma-separated.
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing contact UUID and category.",
            "Usage: !contact category set <uuid> <category>",
        )
    uuid = remaining[0]
    category = remaining[1]
    svc: ContactService = get_contact_service()
    svc.update(uuid, {"category": category})
    return {"type": "status", "title": "Category Set", "data": {"uuid": uuid[:8], "category": category}}


@command("contact.category.add")
def contact_category_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact category add <uuid> <category>

    Appends a category to a contact's existing categories.
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing contact UUID and category.",
            "Usage: !contact category add <uuid> <category>",
        )
    uuid = remaining[0]
    category = remaining[1]
    svc: ContactService = get_contact_service()
    contact = svc.get(uuid)
    if not contact:
        raise CommandValidationError(f"Contact not found: {uuid[:8]}")
    existing = (contact.get("category") or "").strip()
    cats = [c.strip() for c in existing.split(",") if c.strip()]
    if category not in cats:
        cats.append(category)
    svc.update(uuid, {"category": ",".join(cats)})
    return {"type": "status", "title": "Category Added", "data": {"uuid": uuid[:8], "category": category}}


@command("contact.category.remove")
def contact_category_remove(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!contact category remove <uuid> <category>

    Removes a category from a contact's existing categories.
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing contact UUID and category.",
            "Usage: !contact category remove <uuid> <category>",
        )
    uuid = remaining[0]
    category = remaining[1]
    svc: ContactService = get_contact_service()
    contact = svc.get(uuid)
    if not contact:
        raise CommandValidationError(f"Contact not found: {uuid[:8]}")
    existing = (contact.get("category") or "").strip()
    cats = [c.strip() for c in existing.split(",") if c.strip() and c.strip() != category]
    svc.update(uuid, {"category": ",".join(cats)})
    return {"type": "status", "title": "Category Removed", "data": {"uuid": uuid[:8], "category": category}}
