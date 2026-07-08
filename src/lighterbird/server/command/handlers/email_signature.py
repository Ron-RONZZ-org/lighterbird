"""Command handlers for the ``!email signature`` domain.

Manages global named signatures (decoupled from accounts).
"""

from __future__ import annotations

from typing import Any

from lighterbird.email.service import EmailService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service


@command("email.signature.list")
def signature_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature list

    List all configured signatures.
    """
    svc: EmailService = get_email_service()
    sigs = svc.signatures.list_signatures()

    # Enrich each signature with account default info
    accounts = svc.list_accounts()
    account_defaults: dict[str, list[str]] = {}
    for acct in accounts:
        default_uuid = svc.signatures.get_account_default_uuid(acct["email"])
        if default_uuid:
            account_defaults.setdefault(default_uuid, []).append(acct["email"])

    enriched = []
    for sig in sigs:
        entry = dict(sig)
        default_for = account_defaults.get(sig["uuid"], [])
        if default_for:
            entry["default_for"] = default_for
        enriched.append(entry)

    return {
        "type": "status",
        "title": "Email Signatures",
        "data": {"signatures": enriched},
    }


@command("email.signature.add",
         params=[
             {"name": "name", "type": "string", "help": "Unique signature name (e.g. work, personal)", "required": True},
             {"name": "text", "type": "string", "help": "Signature text (plain text or HTML)"},
         ],
         interactive=True)
def signature_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature add <name> <text>

    Add a new global named signature.
    ``<name>`` is a unique label (e.g. "work", "personal").
    ``<text>`` is the signature content (plain text or HTML).
    """
    if len(remaining) < 1:
        raise CommandValidationError(
            "Missing required args: <name> <text>",
            "Usage: !email signature add work \"Best regards\\nJohn\"",
        )
    name = remaining[0]
    text = " ".join(remaining[1:]) if len(remaining) > 1 else ""

    svc: EmailService = get_email_service()

    try:
        sig = svc.signatures.create(name, text)
    except ValueError as e:
        raise CommandValidationError(str(e))

    return {
        "type": "status",
        "title": "Signature Added",
        "data": sig,
    }


@command("email.signature.modify",
         params=[
             {"name": "uuid", "type": "uuid", "help": "Signature UUID", "required": True},
         ],
         flags=[
             {"name": "name", "type": "string", "help": "New signature name"},
             {"name": "text", "type": "string", "help": "New signature text"},
         ],
         interactive=True)
def signature_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature modify <uuid> [--name NAME] [--text TEXT]

    Update a signature's name and/or text by UUID.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing signature UUID.",
            "Usage: !email signature modify <uuid> [--name NAME] [--text TEXT]",
        )
    uuid_ = remaining[0]
    name = flags.get("name", None)
    text = flags.get("text", None)

    if name is None and text is None:
        raise CommandValidationError(
            "Nothing to change. Provide --name and/or --text.",
        )

    svc: EmailService = get_email_service()
    try:
        sig = svc.signatures.update(uuid_, name=name, signature_text=text)
    except ValueError as e:
        raise CommandValidationError(str(e))

    if not sig:
        raise CommandValidationError(f"Signature not found: {uuid_}")

    return {
        "type": "status",
        "title": "Signature Updated",
        "data": sig,
    }


@command("email.signature.delete")
def signature_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature delete <uuid>

    Delete a signature by UUID.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing signature UUID.",
            "Usage: !email signature delete <uuid>",
        )
    uuid_ = remaining[0]

    svc: EmailService = get_email_service()
    if svc.signatures.delete(uuid_):
        return {"type": "status", "title": "Signature Deleted", "data": {"uuid": uuid_}}
    raise CommandValidationError(f"Signature not found: {uuid_}")


@command("email.signature.default")
def signature_default(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature default <email> [--uuid UUID]

    Show or set the default signature for an account.
    Without ``--uuid``, shows the current default.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing account email.",
            "Usage: !email signature default user@example.com [--uuid UUID]",
        )
    email_addr = remaining[0]

    svc: EmailService = get_email_service()
    acct = svc.get_account(email_addr)
    if not acct:
        raise CommandValidationError(
            f"Account not found: {email_addr}",
            "Use !email account list to see available accounts.",
        )

    uuid_override = flags.get("uuid", None)
    if uuid_override:
        # Verify the signature exists
        sig = svc.signatures.get(uuid_override)
        if not sig:
            raise CommandValidationError(
                f"Signature not found: {uuid_override}",
            )
        svc.signatures.set_account_default(email_addr, uuid_override)
        return {
            "type": "status",
            "title": "Default Signature Set",
            "data": {"email": email_addr, "default_signature_uuid": uuid_override,
                     "name": sig["name"]},
        }

    # Show current default
    default_uuid = svc.signatures.get_account_default_uuid(email_addr)
    if default_uuid:
        sig = svc.signatures.get(default_uuid)
        return {
            "type": "status",
            "title": "Default Signature",
            "data": sig or {"email": email_addr, "signature": ""},
        }
    return {
        "type": "status",
        "title": "No Default Signature",
        "data": {"email": email_addr, "signature": ""},
    }
