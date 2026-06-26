"""Command handlers for ``!email sieve <subcommand>``.

Registered paths:
    - email.sieve.list
    - email.sieve.view
    - email.sieve.add
    - email.sieve.modify
    - email.sieve.delete
    - email.sieve.activate
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service
from lighterbird.email.service import EmailService


def _resolve_account(
    svc: EmailService,
    account_uuid: str = "",
) -> str:
    """Resolve account UUID, defaulting to first with ManageSieve."""
    if account_uuid:
        return account_uuid
    accounts = svc.list_accounts()
    if not accounts:
        raise CommandValidationError(
            "No email accounts configured.",
            "Add one with: !email account add",
        )
    for acct in accounts:
        if acct.get("managesieve_host", ""):
            return acct["uuid"]
    return accounts[0]["uuid"]


def _script_to_dict(script: dict) -> dict:
    """Normalize a DB script row to a response dict."""
    return {
        "uuid": script["uuid"],
        "account_uuid": script["konto_id"],
        "name": script["nomo"],
        "content": script.get("content", ""),
        "active": bool(script.get("active", 0)),
        "system": bool(script.get("system", 0)),
        "man_sync": bool(script.get("man_sync", 1)),
        "created_at": script.get("kreita_je", ""),
        "modified_at": script.get("modifita_je", ""),
    }


@command("email.sieve")
def sieve_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve — Show available sieve subcommands."""
    return {
        "type": "status",
        "title": "Sieve Commands",
        "data": {
            "_summary": (
                "Available !email sieve commands:\n"
                "  !email sieve list                  — List Sieve scripts\n"
                "  !email sieve view <name>           — View script content\n"
                "  !email sieve add <name> [content]  — Create a new script\n"
                "  !email sieve modify <name>         — Modify a script\n"
                "  !email sieve delete <name> [...]   — Delete script(s)\n"
                "  !email sieve activate <name>       — Activate a script\n"
                "\n"
                "Use --account <uuid> to scope to a specific email account.\n"
                "Use --active flag with add/modify to activate immediately."
            ),
        },
    }


@command("email.sieve.list")
def sieve_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve list [--account <uuid>]"""
    svc: EmailService = get_email_service()
    account_uuid = _resolve_account(svc, flags.get("account", ""))
    scripts = svc.sieve.list_scripts(konto_id=account_uuid)
    return {
        "type": "sieve-list",
        "title": "Sieve Scripts",
        "data": {
            "scripts": [_script_to_dict(s) for s in scripts],
            "total": len(scripts),
        },
    }


@command("email.sieve.view")
def sieve_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve view <name> [--account <uuid>]"""
    if not remaining:
        raise CommandValidationError(
            "Missing script name.",
            "Usage: !email sieve view <name> [--account <uuid>]",
        )
    name = remaining[0]
    svc: EmailService = get_email_service()
    account_uuid = _resolve_account(svc, flags.get("account", ""))
    script = svc.sieve.get_script(name, konto_id=account_uuid)
    if not script:
        raise CommandValidationError(
            f"Sieve script '{name}' not found.",
            f"List available scripts: !email sieve list --account {account_uuid[:8]}",
        )
    return {
        "type": "status",
        "title": f"Sieve: {name}",
        "data": _script_to_dict(script),
    }


@command("email.sieve.add")
def sieve_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve add <name> [content] [--account <uuid>] [--active]"""
    if not remaining:
        raise CommandValidationError(
            "Missing script name.",
            "Usage: !email sieve add <name> [content] [--account <uuid>] [--active]",
        )
    name = remaining[0]
    content = " ".join(remaining[1:]) if len(remaining) > 1 else ""
    active = "active" in flags
    svc: EmailService = get_email_service()
    account_uuid = _resolve_account(svc, flags.get("account", ""))

    try:
        script = svc.sieve.create_script(
            konto_id=account_uuid,
            nomo=name,
            content=content,
            active=active,
        )
    except ValueError as e:
        raise CommandValidationError(str(e))

    return {
        "type": "status",
        "title": "Script Created",
        "data": _script_to_dict(script),
    }


@command("email.sieve.modify")
def sieve_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve modify <name> [content] [--account <uuid>] [--active] [--name NEW_NAME] [--man-sync yes|no]"""
    if not remaining:
        raise CommandValidationError(
            "Missing script name.",
            "Usage: !email sieve modify <name> [content] [--account <uuid>] [--active] [--name NEW_NAME]",
        )
    name = remaining[0]
    svc: EmailService = get_email_service()
    account_uuid = _resolve_account(svc, flags.get("account", ""))

    content = " ".join(remaining[1:]) if len(remaining) > 1 else None
    active: bool | None = None
    if "active" in flags:
        active = True
    man_sync: bool | None = None
    if "man-sync" in flags:
        val = flags["man-sync"].lower()
        if val in ("yes", "true", "1"):
            man_sync = True
        elif val in ("no", "false", "0"):
            man_sync = False
    new_name = flags.get("name", None)

    try:
        script = svc.sieve.update_script(
            nomo=name,
            konto_id=account_uuid,
            new_name=new_name,
            content=content,
            active=active,
            man_sync=man_sync,
        )
    except ValueError as e:
        raise CommandValidationError(str(e))

    if not script:
        raise CommandValidationError(
            f"Sieve script '{name}' not found.",
            f"List available scripts: !email sieve list --account {account_uuid[:8]}",
        )

    return {
        "type": "status",
        "title": "Script Modified",
        "data": _script_to_dict(script),
    }


@command("email.sieve.delete")
def sieve_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve delete <name> [name...] [--account <uuid>]"""
    if not remaining:
        raise CommandValidationError(
            "Missing script name(s).",
            "Usage: !email sieve delete <name> [name...] [--account <uuid>]",
        )
    svc: EmailService = get_email_service()
    account_uuid = _resolve_account(svc, flags.get("account", ""))
    succeeded = []
    failed = []
    for name in remaining:
        try:
            if svc.sieve.delete_script(name, konto_id=account_uuid):
                succeeded.append(name)
            else:
                failed.append(name)
        except ValueError as e:
            failed.append(f"{name} ({e})")

    return {
        "type": "status",
        "title": "Script(s) Deleted",
        "data": {"deleted": succeeded, "failed": failed},
    }


@command("email.sieve.activate")
def sieve_activate(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve activate <name> [--account <uuid>]"""
    if not remaining:
        raise CommandValidationError(
            "Missing script name.",
            "Usage: !email sieve activate <name> [--account <uuid>]",
        )
    name = remaining[0]
    svc: EmailService = get_email_service()
    account_uuid = _resolve_account(svc, flags.get("account", ""))
    script = svc.sieve.activate_script(name, konto_id=account_uuid)
    if not script:
        raise CommandValidationError(
            f"Sieve script '{name}' not found.",
            f"List available scripts: !email sieve list --account {account_uuid[:8]}",
        )
    return {
        "type": "status",
        "title": "Script Activated",
        "data": _script_to_dict(script),
    }
