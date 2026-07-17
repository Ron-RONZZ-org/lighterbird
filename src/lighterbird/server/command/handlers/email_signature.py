"""Command handlers for the ``!email signature`` domain.

Manages global named signatures (decoupled from accounts).
"""

from __future__ import annotations

from typing import Any

from lightercore.permissions import PermissionLevel
from lighterbird.email.service import EmailService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service


@command("email.signature.list", permission_level=PermissionLevel.READ)
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
        "type": "signature-list",
        "title": "Email Signatures",
        "data": {"signatures": enriched, "total": len(enriched)},
    }


@command("email.signature.add",
         params=[
             {"name": "name", "type": "string", "help": "Unique signature name (e.g. work, personal)", "required": True,
              "width": "50%"},
             {"name": "text", "type": "string", "help": "Signature text (plain text or HTML)",
              "multiline": True},
         ],
         flags=[
             {"name": "format", "type": "string", "help": "Signature format: plain, html, or markdown",
              "values": ["plain", "html", "markdown"], "width": "50%"},
         ],
         interactive=True)
def signature_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature add <name> <text> [--format plain|html|markdown]

    Add a new global named signature.
    ``<name>`` is a unique label (e.g. "work", "personal").
    ``<text>`` is the signature content.
    ``--format`` specifies the format: ``plain`` (default), ``html``, or ``markdown``.
    """
    if len(remaining) < 1:
        raise CommandValidationError(
            "Missing required args: <name> <text>",
            "Usage: !email signature add work \"Best regards\\nJohn\" [--format markdown]",
        )
    name = remaining[0]
    text = " ".join(remaining[1:]) if len(remaining) > 1 else ""
    sig_format = flags.get("format", "plain")

    if sig_format not in ("plain", "html", "markdown"):
        raise CommandValidationError(
            f"Invalid format: {sig_format}. Must be 'plain', 'html', or 'markdown'."
        )

    svc: EmailService = get_email_service()

    try:
        sig = svc.signatures.create(name, text, signature_format=sig_format)
    except ValueError as e:
        raise CommandValidationError(str(e))

    return {
        "type": "status",
        "title": "Signature Added",
        "data": sig,
    }


def _resolve_signature(svc: EmailService, identifier: str) -> dict | None:
    """Resolve a signature by name (first) or UUID (fallback).

    Args:
        svc: EmailService instance.
        identifier: Signature name or UUID.

    Returns:
        Signature dict or None if not found.
    """
    # Try name first (named signatures are user-facing)
    sig = svc.signatures.get_by_name(identifier)
    if sig:
        return sig
    # Fallback: treat as UUID
    return svc.signatures.get(identifier)


@command("email.signature.modify",
         params=[
             {"name": "name", "type": "string", "help": "Signature name (or UUID)", "required": True,
              "uuidSource": "email.signatures"},
         ],
         flags=[
             {"name": "name", "type": "string", "help": "New signature name"},
             {"name": "text", "type": "string", "help": "New signature text",
              "multiline": True},
             {"name": "format", "type": "string", "help": "Signature format: plain, html, or markdown",
              "values": ["plain", "html", "markdown"]},
         ],
         interactive=True)
def signature_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature modify <name-or-uuid> [--name NAME] [--text TEXT] [--format plain|html|markdown]

    Update a signature by name (or UUID). When invoked interactively without
    modification flags, returns a ``form-required`` response with existing
    data pre-filled for editing.
    """
    svc: EmailService = get_email_service()

    if not remaining:
        # Interactive form open — no identifier yet; return blank form
        return {
            "type": "form-required",
            "title": "Modify Signature",
            "data": {
                "form": "email-signature-modify",
                "initialData": {},
            },
        }

    identifier = remaining[0]
    name = flags.get("name", None)
    text = flags.get("text", None)
    sig_format = flags.get("format", None)

    if sig_format is not None and sig_format not in ("plain", "html", "markdown"):
        raise CommandValidationError(
            f"Invalid format: {sig_format}. Must be 'plain', 'html', or 'markdown'."
        )

    # If only identifier provided (no modification flags), fetch existing
    # data and return form-required with autofill for the interactive form.
    if name is None and text is None and sig_format is None:
        sig = _resolve_signature(svc, identifier)
        if not sig:
            raise CommandValidationError(f"Signature not found: {identifier}")
        return {
            "type": "form-required",
            "title": "Modify Signature",
            "data": {
                "form": "email-signature-modify",
                "initialData": {
                    "name": sig.get("name", identifier),
                    "text": sig.get("signature_text", ""),
                    "format": sig.get("signature_format", "plain"),
                },
            },
        }

    # Modification with flags — apply changes
    sig = _resolve_signature(svc, identifier)
    if not sig:
        raise CommandValidationError(f"Signature not found: {identifier}")
    sig_uuid = sig["uuid"]

    try:
        updated = svc.signatures.update(sig_uuid, name=name, signature_text=text,
                                         signature_format=sig_format)
    except ValueError as e:
        raise CommandValidationError(str(e))

    if not updated:
        raise CommandValidationError(f"Signature not found: {identifier}")

    return {
        "type": "status",
        "title": "Signature Updated",
        "data": updated,
    }


@command("email.signature.delete",
         params=[
             {"name": "uuid", "type": "string",
              "help": "Signature UUID or name", "required": True,
              "uuidSource": "email.signatures"},
         ])
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


@command("email.signature.default",
         params=[
             {"name": "email", "type": "string",
              "help": "Account email address", "required": True},
         ],
         flags=[
             {"name": "uuid", "type": "string",
              "help": "Signature UUID to set as default",
              "uuidSource": "email.signatures"},
         ],
         interactive=True)
def signature_default(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature default <email> [--uuid UUID]

    Show or set the default signature for an account.
    Without ``--uuid``, shows the current default.
    When invoked without args (interactive), opens a form with
    account email dropdown and signature autocomplete.
    """
    svc: EmailService = get_email_service()

    # Interactive mode: no args → return form-required
    if not remaining and not flags.get("uuid"):
        accounts = svc.list_accounts()
        sigs = svc.signatures.list_signatures()
        return {
            "type": "form-required",
            "title": "Set Default Signature",
            "data": {
                "form": "email-signature-default",
                "initialData": {},
                "accounts": [{"email": a["email"], "name": a.get("name", "")} for a in accounts],
                "signatures": [{"uuid": s["uuid"], "name": s["name"]} for s in sigs],
            },
        }

    if not remaining:
        raise CommandValidationError(
            "Missing account email.",
            "Usage: !email signature default user@example.com [--uuid UUID]",
        )
    email_addr = remaining[0]

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
