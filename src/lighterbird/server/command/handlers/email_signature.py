"""Command handlers for the ``!email signature`` domain.

Manages named signatures per account in the ``email_signatures`` table.
"""

from __future__ import annotations

from typing import Any

from lighterbird.email.service import EmailService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service


@command("email.signature.list")
def signature_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature list [--account <email>]

    List signatures for all accounts, or filter by a specific account.
    """
    svc: EmailService = get_email_service()
    account_filter = flags.get("account", "")
    if account_filter:
        sigs = svc.signatures.list_signatures(account_email=account_filter)
    else:
        sigs = svc.signatures.list_signatures()

    return {
        "type": "status",
        "title": "Email Signatures",
        "data": {"signatures": sigs},
    }


@command("email.signature.add",
         params=[
             {"name": "email", "type": "string", "help": "Account email", "required": True},
             {"name": "name", "type": "string", "help": "Unique signature name (e.g. work, personal)", "required": True},
             {"name": "text", "type": "string", "help": "Signature text (plain text or HTML)"},
         ],
         interactive=True)
def signature_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature add <email> <name> <text>

    Add a new named signature for an account.
    ``<name>`` is a unique label (e.g. "work", "personal", "default").
    ``<text>`` is the signature content (plain text or HTML).

    Name must be unique per account.
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing required args: <email> <name> <text>",
            "Usage: !email signature add user@example.com work \"Best regards\\nJohn\"",
        )
    email_addr = remaining[0]
    name = remaining[1]
    text = " ".join(remaining[2:]) if len(remaining) > 2 else ""

    svc: EmailService = get_email_service()
    acct = svc.get_account(email_addr)
    if not acct:
        raise CommandValidationError(
            f"Account not found: {email_addr}",
            "Use !email account list to see available accounts.",
        )

    try:
        sig = svc.signatures.create(email_addr, name, text)
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
    """!email signature default <email> [--name NAME]

    Show or set the default signature for an account.
    Without ``--name``, shows the current default.

    The default is identified by the name ``default``.  This command
    renames an existing signature to ``default``.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing account email.",
            "Usage: !email signature default user@example.com [--name NAME]",
        )
    email_addr = remaining[0]

    svc: EmailService = get_email_service()
    acct = svc.get_account(email_addr)
    if not acct:
        raise CommandValidationError(
            f"Account not found: {email_addr}",
            "Use !email account list to see available accounts.",
        )

    name_override = flags.get("name", None)
    if name_override:
        # Rename the named signature to "default" (removes old default via UNIQUE)
        target = svc.signatures.get_by_name(email_addr, name_override)
        if not target:
            raise CommandValidationError(
                f"Signature '{name_override}' not found for {email_addr}.",
            )
        old_default = svc.signatures.get_default(email_addr)
        if old_default:
            svc.signatures.update(old_default["uuid"], name=name_override)
        svc.signatures.update(target["uuid"], name="default")
        return {
            "type": "status",
            "title": "Default Signature Set",
            "data": {"email": email_addr, "name": "default"},
        }

    default = svc.signatures.get_default(email_addr)
    if not default:
        return {
            "type": "status",
            "title": "No Default Signature",
            "data": {"email": email_addr, "signature": ""},
        }
    return {
        "type": "status",
        "title": "Default Signature",
        "data": default,
    }
