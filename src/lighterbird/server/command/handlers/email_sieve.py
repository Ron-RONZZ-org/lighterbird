"""Command handlers for ``!email sieve <subcommand>``.

Registered paths:
    - email.sieve.list
    - email.sieve.view
    - email.sieve.add
    - email.sieve.modify
    - email.sieve.delete
    - email.sieve.activate
    - email.sieve.deactivate
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service
from lighterbird.email.service import EmailService


def _resolve_account(
    svc: EmailService,
    identifier: str = "",
) -> str:
    """Resolve an account by UUID prefix or email address.

    Raises CommandValidationError if not found or no accounts exist.
    """
    if not identifier:
        raise CommandValidationError(
            "Missing --account flag. Specify an account UUID or email address:\n"
            "  !email sieve activate <name> --account user@example.com",
        )
    accounts = svc.list_accounts()
    if not accounts:
        raise CommandValidationError(
            "No email accounts configured.",
            "Add one with: !email account add",
        )
    # Try exact UUID match
    for acct in accounts:
        if acct["uuid"] == identifier:
            return acct["uuid"]
    # Try email match
    identifier_lower = identifier.lower().strip()
    for acct in accounts:
        if acct.get("retposto", "").lower() == identifier_lower:
            return acct["uuid"]
    # Try UUID prefix
    for acct in accounts:
        if acct["uuid"].startswith(identifier):
            return acct["uuid"]
    raise CommandValidationError(
        f"Account '{identifier}' not found.",
        "Use !email account list to see available accounts.",
    )


def _script_to_dict(script: dict) -> dict:
    """Normalize a script row to a response dict."""
    result = {
        "uuid": script["uuid"],
        "name": script["name"],
        "content": script.get("content", ""),
        "system": bool(script.get("system", 0)),
        "created_at": script.get("created_at", ""),
        "modified_at": script.get("modified_at", ""),
    }
    if script.get("aktivado"):
        result["aktivado"] = script["aktivado"]
    return result


@command("email.sieve")
def sieve_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve — Show available sieve subcommands."""
    return {
        "type": "status",
        "title": "Sieve Commands",
        "data": {
            "_summary": (
                "Available !email sieve commands:\n"
                "  !email sieve list [--account <email>]\n"
                "      List all scripts (with activation status per account)\n"
                "  !email sieve view <name> [--account <email>]\n"
                "      View script content (with activation status)\n"
                "  !email sieve add <name> --file <path>\n"
                "      Create a script from a local file\n"
                "  !email sieve modify <name> --file <path> [--name NEW_NAME]\n"
                "      Update a script from a local file\n"
                "  !email sieve delete <name> [name...]\n"
                "      Delete script(s) globally\n"
                "  !email sieve activate <name> --account <email>\n"
                "      Activate a script on a specific account\n"
                "  !email sieve deactivate <name> --account <email>\n"
                "      Deactivate a script on a specific account\n"
                "\n"
                "Scripts are stored globally and can be activated on multiple accounts.\n"
                "Use --account with an email address or UUID."
            ),
        },
    }


@command("email.sieve.list")
def sieve_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve list [--account <email>]

    Lists all global scripts. When ``--account`` is given, shows per-account
    activation status and appends the virtual ``_spam_blocks`` script.
    """
    svc: EmailService = get_email_service()
    account_id = flags.get("account", "")
    resolved_id = _resolve_account(svc, account_id) if account_id else ""
    scripts = svc.sieve.list_scripts(konto_id=resolved_id or None)
    return {
        "type": "sieve-list",
        "title": "Sieve Scripts",
        "data": {
            "scripts": [_script_to_dict(s) for s in scripts],
            "total": len(scripts),
            "account_filter": resolved_id,
        },
    }


@command("email.sieve.view")
def sieve_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve view <name> [--account <email>]

    Views a script. With ``--account``, shows activation status for that account.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing script name.",
            "Usage: !email sieve view <name> [--account <email>]",
        )
    name = remaining[0]
    svc: EmailService = get_email_service()
    account_id = flags.get("account", "")
    resolved_id = _resolve_account(svc, account_id) if account_id else ""

    if resolved_id:
        script = svc.sieve.get_script_with_activation(name, konto_id=resolved_id)
    else:
        script = svc.sieve.get_script(name)
    if not script:
        raise CommandValidationError(
            f"Sieve script '{name}' not found.",
            "List available scripts: !email sieve list",
        )
    return {
        "type": "status",
        "title": f"Sieve: {name}",
        "data": _script_to_dict(script),
    }


def _read_file_content(file_path: str) -> str:
    """Read content from a file path, with clear error on failure."""
    try:
        with open(file_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        raise CommandValidationError(
            f"File not found: {file_path}",
            "Check the path and try again.",
        )
    except IsADirectoryError:
        raise CommandValidationError(
            f"Path is a directory, not a file: {file_path}",
        )
    except PermissionError:
        raise CommandValidationError(
            f"Permission denied: {file_path}",
        )
    except UnicodeDecodeError:
        raise CommandValidationError(
            f"File is not valid UTF-8 text: {file_path}",
        )


@command("email.sieve.add")
def sieve_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve add <name> [--file /path/to/script.sieve]

    Creates a new global script. Provide the Sieve source via ``--file``
    (recommended) or use the GUI editor (``!email sieve add <name>`` with
    no ``--file`` opens the interactive editor).
    """
    if not remaining:
        raise CommandValidationError(
            "Missing script name.",
            "Usage: !email sieve add <name> --file /path/to/script.sieve",
        )
    name = remaining[0]
    svc: EmailService = get_email_service()

    if "file" in flags:
        content = _read_file_content(flags["file"])
    else:
        # In CLI mode, empty content is fine — user can edit via GUI later.
        # The interactive flag in the command tree will open the editor.
        content = ""

    try:
        script = svc.sieve.create_script(nomo=name, content=content)
    except ValueError as e:
        raise CommandValidationError(str(e))

    return {
        "type": "status",
        "title": "Script Created",
        "data": _script_to_dict(script),
    }


@command("email.sieve.modify")
def sieve_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve modify <name> [--file /path/to/script.sieve] [--name NEW_NAME]

    Updates a script. Use ``--file`` to load new content from a file,
    or omit it to keep the current content (open GUI editor to edit).
    """
    if not remaining:
        raise CommandValidationError(
            "Missing script name.",
            "Usage: !email sieve modify <name> [--file /path/to/script.sieve] [--name NEW_NAME]",
        )
    name = remaining[0]
    svc: EmailService = get_email_service()

    content: str | None = None
    if "file" in flags:
        content = _read_file_content(flags["file"])
    new_name = flags.get("name", None)

    try:
        script = svc.sieve.update_script(
            nomo=name, new_name=new_name, content=content,
        )
    except ValueError as e:
        raise CommandValidationError(str(e))

    if not script:
        raise CommandValidationError(
            f"Sieve script '{name}' not found.",
            "List available scripts: !email sieve list",
        )
    return {
        "type": "status",
        "title": "Script Modified",
        "data": _script_to_dict(script),
    }


@command("email.sieve.delete")
def sieve_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve delete <name> [name...]

    Deletes script(s) globally (removes from all accounts).
    """
    if not remaining:
        raise CommandValidationError(
            "Missing script name(s).",
            "Usage: !email sieve delete <name> [name...]",
        )
    svc: EmailService = get_email_service()
    succeeded = []
    failed = []
    for name in remaining:
        try:
            if svc.sieve.delete_script(name):
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
    """!email sieve activate <name> --account <email>

    Activates a script on a specific account.
    ``--account`` accepts an email address or account UUID.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing script name.",
            "Usage: !email sieve activate <name> --account <email>",
        )
    name = remaining[0]
    account_id = flags.get("account", "")
    if not account_id:
        raise CommandValidationError(
            "Missing --account flag.",
            "Usage: !email sieve activate <name> --account user@example.com",
        )
    svc: EmailService = get_email_service()
    resolved_id = _resolve_account(svc, account_id)

    script = svc.sieve.activate_script(name, konto_id=resolved_id)
    if not script:
        raise CommandValidationError(
            f"Sieve script '{name}' not found.",
            "List available scripts: !email sieve list",
        )
    return {
        "type": "status",
        "title": "Script Activated",
        "data": _script_to_dict(script),
    }


@command("email.sieve.deactivate")
def sieve_deactivate(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email sieve deactivate <name> --account <email>

    Deactivates a script on a specific account.
    ``--account`` accepts an email address or account UUID.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing script name.",
            "Usage: !email sieve deactivate <name> --account <email>",
        )
    name = remaining[0]
    account_id = flags.get("account", "")
    if not account_id:
        raise CommandValidationError(
            "Missing --account flag.",
            "Usage: !email sieve deactivate <name> --account user@example.com",
        )
    svc: EmailService = get_email_service()
    resolved_id = _resolve_account(svc, account_id)

    script = svc.sieve.deactivate_script(name, konto_id=resolved_id)
    if not script:
        raise CommandValidationError(
            f"Sieve script '{name}' not found.",
            "List available scripts: !email sieve list",
        )
    return {
        "type": "status",
        "title": "Script Deactivated",
        "data": _script_to_dict(script),
    }
