"""Command handlers for the ``!email sieve`` domain.

Handles script CRUD and per-account activation using natural keys
(script names and account emails).
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service
from lighterbird.email.service import EmailService


def _resolve_account_identifier(identifier: str) -> str | None:
    """Resolve a user-supplied account identifier to an email.

    Accepts email, or prefix. Returns email or None.
    """
    if not identifier:
        return None
    svc: EmailService = get_email_service()
    # Try direct email lookup
    acct = svc.get_account(identifier)
    if acct:
        return identifier
    # Try prefix match on email
    matches = svc.db.execute(
        "SELECT email FROM accounts WHERE email LIKE ? LIMIT 10",
        (f"{identifier}%",),
    )
    if len(matches) == 1:
        return matches[0]["email"]
    return None


@command("email.sieve")
def sieve_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve — Show sieve subcommands"""
    return {
        "type": "status",
        "title": "Sieve Commands",
        "data": {
            "_summary": (
                "Available !email sieve commands:\n"
                "  !email sieve list [--account email]        — List scripts\n"
                "  !email sieve add <name> [--content ...|--file path]\n"
                "  !email sieve modify <name> [--new-name N] [--content ...|--file path]\n"
                "  !email sieve delete <name>\n"
                "  !email sieve activate <name> --account email [--priority N]\n"
                "  !email sieve deactivate <name> --account email"
            ),
        },
    }


@command("email.sieve.list")
def sieve_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve list [--account email]"""
    svc: EmailService = get_email_service()
    account_id = flags.get("account", "")
    resolved_id = _resolve_account_identifier(account_id) if account_id else None
    scripts = svc.sieve.list_scripts(account_email=resolved_id or None)
    return {"type": "status", "title": "Sieve Scripts", "data": {"scripts": scripts}}


@command("email.sieve.view")
def sieve_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve view <name> [--account email]"""
    if not remaining:
        raise CommandValidationError(
            "Missing script name.", "Usage: !email sieve view <name> [--account email]"
        )
    name = remaining[0]
    svc: EmailService = get_email_service()
    account_id = flags.get("account", "")
    resolved_id = _resolve_account_identifier(account_id) if account_id else None
    if resolved_id:
        script = svc.sieve.get_script_with_activation(name, account_email=resolved_id)
    else:
        script = svc.sieve.get_script(name)
    if not script:
        raise CommandValidationError(f"Script not found: {name}")
    return {"type": "status", "title": f"Sieve: {name}", "data": script}


@command("email.sieve.add")
def sieve_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve add <name> [--content \"...\"] [--file path]"""
    from pathlib import Path

    if not remaining:
        raise CommandValidationError(
            "Missing script name.", "Usage: !email sieve add <name> [--content ...|--file path]"
        )
    name = remaining[0]
    content = flags.get("content", "")
    file_path = flags.get("file", "")

    if file_path:
        p = Path(file_path)
        if not p.exists():
            raise CommandValidationError(f"File not found: {file_path}")
        content = p.read_text("utf-8")

    if not content:
        # No content provided — open form
        return {
            "type": "form",
            "title": "New Sieve Script",
            "data": {
                "fields": [
                    {"name": "name", "label": "Script Name", "value": name, "readonly": True},
                    {"name": "content", "label": "Sieve Content", "value": "", "multiline": True, "language": "sieve"},
                ],
                "submit": "email.sieve.add",
            },
        }

    svc: EmailService = get_email_service()
    try:
        script = svc.sieve.create_script(name=name, content=content)
    except ValueError as e:
        raise CommandValidationError(str(e))
    return {"type": "status", "title": "Script Created", "data": {"name": script["name"]}}


@command("email.sieve.modify")
def sieve_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve modify <name> [--new-name N] [--content ...|--file path]"""
    from pathlib import Path

    if not remaining:
        raise CommandValidationError(
            "Missing script name.", "Usage: !email sieve modify <name> [--new-name N] [--content ...|--file path]"
        )
    name = remaining[0]
    new_name = flags.get("name", None) or flags.get("new-name", None)
    content = flags.get("content", None)
    file_path = flags.get("file", "")

    if file_path:
        p = Path(file_path)
        if not p.exists():
            raise CommandValidationError(f"File not found: {file_path}")
        content = p.read_text("utf-8")

    svc: EmailService = get_email_service()
    try:
        script = svc.sieve.update_script(name, new_name=new_name, content=content)
    except ValueError as e:
        raise CommandValidationError(str(e))
    if not script:
        raise CommandValidationError(f"Script not found: {name}")
    return {"type": "status", "title": "Script Updated", "data": {"name": script["name"]}}


@command("email.sieve.delete")
def sieve_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve delete <name>"""
    if not remaining:
        raise CommandValidationError(
            "Missing script name.", "Usage: !email sieve delete <name>"
        )
    name = remaining[0]
    svc: EmailService = get_email_service()
    if not svc.sieve.delete_script(name):
        raise CommandValidationError(f"Script not found: {name}")
    return {"type": "status", "title": "Script Deleted", "data": {"name": name}}


@command("email.sieve.activate")
def sieve_activate(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve activate <name> --account email [--priority N]"""
    if not remaining:
        raise CommandValidationError(
            "Missing script name.",
            "Usage: !email sieve activate <name> --account email [--priority N]",
        )
    name = remaining[0]
    account_id = flags.get("account", "")
    if not account_id:
        raise CommandValidationError(
            "Missing --account flag.",
            "Usage: !email sieve activate <name> --account email [--priority N]",
        )
    resolved_id = _resolve_account_identifier(account_id)
    if not resolved_id:
        raise CommandValidationError(f"Account not found: {account_id[:20]}")

    priority = int(flags.get("priority", 0))
    svc: EmailService = get_email_service()
    script = svc.sieve.activate_script(name, account_email=resolved_id, priority=priority)
    if not script:
        raise CommandValidationError(f"Script not found: {name}")
    return {"type": "status", "title": "Script Activated", "data": {"name": name, "account": resolved_id}}


@command("email.sieve.deactivate")
def sieve_deactivate(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve deactivate <name> --account email"""
    if not remaining:
        raise CommandValidationError(
            "Missing script name.",
            "Usage: !email sieve deactivate <name> --account email",
        )
    name = remaining[0]
    account_id = flags.get("account", "")
    if not account_id:
        raise CommandValidationError(
            "Missing --account flag.",
            "Usage: !email sieve deactivate <name> --account email",
        )
    resolved_id = _resolve_account_identifier(account_id)
    if not resolved_id:
        raise CommandValidationError(f"Account not found: {account_id[:20]}")

    svc: EmailService = get_email_service()
    script = svc.sieve.deactivate_script(name, account_email=resolved_id)
    if not script:
        raise CommandValidationError(f"Script not found: {name}")
    return {"type": "status", "title": "Script Deactivated", "data": {"name": name, "account": resolved_id}}


@command("email.sieve.priority")
def sieve_priority(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve priority <name> <priority> --account email

    Set execution priority for a script on a specific account.
    Lower priority values are evaluated first.
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing script name or priority.",
            "Usage: !email sieve priority <name> <0-999> --account email",
        )
    name = remaining[0]
    try:
        priority = int(remaining[1])
    except ValueError:
        raise CommandValidationError(
            f"Invalid priority: {remaining[1]}. Must be a number (0-999).",
        )

    account_id = flags.get("account", "")
    if not account_id:
        raise CommandValidationError(
            "Missing --account flag.",
            "Usage: !email sieve priority <name> <priority> --account email",
        )
    resolved_id = _resolve_account_identifier(account_id)
    if not resolved_id:
        raise CommandValidationError(f"Account not found: {account_id[:20]}")

    svc: EmailService = get_email_service()
    result = svc.sieve.set_priority(name, account_email=resolved_id, priority=priority)
    if not result:
        raise CommandValidationError(
            f"Script '{name}' is not activated on {resolved_id}. "
            f"Activate it first with: !email sieve activate {name} --account {resolved_id}"
        )
    return {
        "type": "status",
        "title": "Priority Set",
        "data": {"name": name, "account": resolved_id, "priority": priority},
    }
