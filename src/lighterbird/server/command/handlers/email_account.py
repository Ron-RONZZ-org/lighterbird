"""Command handlers for the ``!email account`` domain.

Handles account CRUD using email as primary key.
"""

from __future__ import annotations

from typing import Any

from lighterbird.email.service import EmailService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service


@command("email.account.list")
def account_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email account list"""
    svc: EmailService = get_email_service()
    accounts = [dict(a) for a in svc.list_accounts()]
    return {"type": "status", "title": "Email Accounts", "data": {"accounts": accounts}}


@command("email.account.add",
         params=[{"name": "email", "type": "string", "help": "user@example.com", "required": True}],
         flags=[
             {"name": "imap", "type": "string", "help": "IMAP server hostname"},
             {"name": "smtp", "type": "string", "help": "SMTP server hostname"},
             {"name": "password", "type": "string", "help": "Account password"},
             {"name": "name", "type": "string", "help": "Display name"},
         ],
         interactive=True)
def account_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email account add <email> [--imap HOST] [--smtp HOST] [--password PW] [--name NAME]

    IMAP/SMTP servers are auto-detected for common providers.
    Only specify --imap or --smtp to override auto-detection.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing email address.",
            "Usage: !email account add user@example.com [--imap imap.example.com] [--smtp smtp.example.com] [--password ...] [--name NAME]",
        )
    email_addr = remaining[0]
    imap_server = flags.get("imap", "")
    smtp_server = flags.get("smtp", "")
    password = flags.get("password", "")
    name = flags.get("name", "")

    from lighterbird.email.server_detect import detect_servers

    detected = detect_servers(email_addr, imap_server=imap_server, smtp_server=smtp_server)
    acct_data = {
        "name": name or email_addr.split("@")[0],
        "email": email_addr.lower().strip(),
        "imap_server": detected["imap"],
        "imap_port": 993,
        "imap_use_ssl": 1,
        "smtp_server": detected["smtp"],
        "smtp_port": 587,
        "smtp_use_tls": 1,
        "imap_username": email_addr,
        "smtp_username": email_addr,
        "managesieve_host": detected.get("managesieve_host", ""),
        "managesieve_port": detected.get("managesieve_port", 4190),
        "managesieve_use_tls": 1,
    }
    svc: EmailService = get_email_service()
    acct = svc.create_account(acct_data, password)
    return {
        "type": "status",
        "title": "Account Added",
        "data": {"email": acct["email"]},
    }


@command("email.account.modify", interactive=True)
def account_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email account modify <email> [--name NAME] [--password PW]
                    [--imap-server HOST] [--smtp-server HOST]
                    [--signature TEXT]

    Modify an existing email account.
    Use ``--signature`` to set or update the account's email signature.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing account email.",
            "Usage: !email account modify <email> [--name ...] [--password ...]",
        )
    email = remaining[0]
    svc: EmailService = get_email_service()
    acct = svc.get_account(email)
    if not acct:
        raise CommandValidationError(f"Account not found: {email}")

    updates = {}
    if "name" in flags:
        updates["name"] = flags["name"]
    if "imap_server" in flags:
        updates["imap_server"] = flags["imap_server"]
    if "smtp_server" in flags:
        updates["smtp_server"] = flags["smtp_server"]
    if "managesieve_host" in flags:
        updates["managesieve_host"] = flags["managesieve_host"]
    if "managesieve_port" in flags:
        raw = flags["managesieve_port"]
        try:
            updates["managesieve_port"] = int(raw)
        except ValueError:
            raise CommandValidationError(f"Invalid managesieve_port: {raw}")
    if "managesieve-use-tls" in flags or "managesieve_use_tls" in flags:
        raw = flags.get("managesieve-use-tls", flags.get("managesieve_use_tls", ""))
        updates["managesieve_use_tls"] = 1 if raw.lower() in ("true", "1", "yes") else 0
    if "signature" in flags:
        updates["signature"] = flags["signature"]
    if updates:
        svc.accounts.update(email, updates)
    if "password" in flags:
        svc.accounts.set_password(email, flags["password"])
    return {"type": "status", "title": "Account Modified", "data": {"email": email}}


@command("email.account.delete", interactive=True)
def account_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email account delete <email> [email...]"""
    if not remaining:
        raise CommandValidationError(
            "Missing email (UUID or address).",
            "Usage: !email account delete <email> [email...]",
        )
    svc: EmailService = get_email_service()
    succeeded = []
    for email_addr in remaining:
        try:
            svc.delete_account(email_addr)
            succeeded.append(email_addr)
        except Exception:
            pass
    return {
        "type": "status",
        "title": "Account(s) Deleted",
        "data": {"removed": succeeded},
    }
