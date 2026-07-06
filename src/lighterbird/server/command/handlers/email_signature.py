"""Command handlers for the ``!email signature`` domain.

Manages per-account email signatures stored in the accounts table.
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
    accounts = svc.list_accounts()

    account_filter = flags.get("account", "")
    if account_filter:
        accounts = [a for a in accounts if a.get("email", "") == account_filter]
        if not accounts:
            raise CommandValidationError(
                f"Account not found: {account_filter}",
                "Use !email account list to see available accounts.",
            )

    signatures = []
    for acct in accounts:
        email = acct.get("email", "")
        name = acct.get("name", "")
        sig = acct.get("signature", "") or ""
        signatures.append({
            "email": email,
            "name": name,
            "signature": sig,
            "has_signature": bool(sig.strip()),
        })

    return {
        "type": "status",
        "title": "Email Signatures",
        "data": {"signatures": signatures},
    }


@command("email.signature.add", interactive=True)
def signature_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature add <email> <text>

    Set the signature for an account.
    ``<text>`` is the signature content (plain text or HTML).
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing required args: <email> <text>",
            "Usage: !email signature add user@example.com \"Sent from my phone\"",
        )
    email_addr = remaining[0]
    text = " ".join(remaining[1:])

    svc: EmailService = get_email_service()
    acct = svc.get_account(email_addr)
    if not acct:
        raise CommandValidationError(
            f"Account not found: {email_addr}",
            "Use !email account list to see available accounts.",
        )

    svc.accounts.update(email_addr, {"signature": text})
    return {
        "type": "status",
        "title": "Signature Set",
        "data": {"email": email_addr, "signature": text},
    }


@command("email.signature.modify", interactive=True)
def signature_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature modify <email> <text>

    Update the signature for an account.
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing required args: <email> <text>",
            "Usage: !email signature modify user@example.com \"New signature text\"",
        )
    email_addr = remaining[0]
    text = " ".join(remaining[1:])

    svc: EmailService = get_email_service()
    acct = svc.get_account(email_addr)
    if not acct:
        raise CommandValidationError(
            f"Account not found: {email_addr}",
            "Use !email account list to see available accounts.",
        )

    svc.accounts.update(email_addr, {"signature": text})
    return {
        "type": "status",
        "title": "Signature Updated",
        "data": {"email": email_addr, "signature": text},
    }


@command("email.signature.delete")
def signature_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email signature delete <email>

    Clear the signature for an account.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing account email.",
            "Usage: !email signature delete user@example.com",
        )
    email_addr = remaining[0]

    svc: EmailService = get_email_service()
    acct = svc.get_account(email_addr)
    if not acct:
        raise CommandValidationError(
            f"Account not found: {email_addr}",
            "Use !email account list to see available accounts.",
        )

    svc.accounts.update(email_addr, {"signature": ""})
    return {
        "type": "status",
        "title": "Signature Deleted",
        "data": {"email": email_addr},
    }
