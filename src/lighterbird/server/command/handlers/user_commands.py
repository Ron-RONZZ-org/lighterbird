"""Command handlers for the ``!user`` domain.

Registered paths:
    - user.saved-commands.list
    - user.saved-commands.add
    - user.saved-commands.modify
    - user.saved-commands.delete
"""

from __future__ import annotations

from typing import Any

from lightercore.permissions import PermissionLevel
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_user_commands_service
from lighterbird.user_commands.service import UserCommandsError, UserCommandsService


@command("user.saved-commands")
def saved_commands_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user saved-commands — Show available subcommands."""
    return {
        "type": "status",
        "title": "Saved Commands",
        "data": {
            "_summary": (
                "Available !user saved-commands subcommands:\n"
                "  !user saved-commands list              — List saved commands\n"
                "  !user saved-commands add               — Add a saved command\n"
                "  !user saved-commands modify <alias>    — Modify a saved command\n"
                "  !user saved-commands remove <alias>    — Remove saved command(s)"
            ),
        },
    }


@command("user.saved-commands.list", permission_level=PermissionLevel.READ)
def saved_commands_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user saved-commands list — List all saved commands."""
    svc: UserCommandsService = get_user_commands_service()
    commands = svc.list_all()

    # Normalize for frontend display
    items = []
    for cmd in commands:
        items.append({
            "uuid": cmd["uuid"],
            "alias": cmd["alias"],
            "command_template": cmd["command_template"],
            "hint": cmd["hint"],
            "created_at": cmd["created_at"],
            "modified_at": cmd["modified_at"],
        })

    return {
        "type": "saved-commands",
        "title": "Saved Commands",
        "data": {"commands": items, "total": len(items)},
    }


@command("user.saved-commands.add", interactive=True)
def saved_commands_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user saved-commands add [--alias ALIAS] [--command TEMPLATE] [--hint HINT]

    Add a new saved command alias.

    The ``--command`` template stores the command WITHOUT the leading ``!``.
    Use ``$1``, ``$2``, etc. for positional arguments.

    Example::

        !user saved-commands add --alias ronzz --command "email list --folder ron@ronzz.org/$1" --hint "open ron@ronzz.org folder"
    """
    alias = flags.get("alias", "")
    command_template = flags.get("command", "")
    hint = flags.get("hint", "")

    if not alias:
        raise CommandValidationError(
            "Missing --alias flag.",
            "Usage: !user saved-commands add --alias ronzz --command \"email list --folder X\" [--hint ...]",
        )
    if not command_template:
        raise CommandValidationError(
            "Missing --command flag.",
            "Usage: !user saved-commands add --alias ronzz --command \"email list --folder X\"",
        )

    svc: UserCommandsService = get_user_commands_service()
    try:
        result = svc.create(alias, command_template, hint)
    except UserCommandsError as e:
        raise CommandValidationError(str(e))
    except Exception as e:
        raise CommandValidationError(
            f"Failed to save command: {e}",
            "Check that the alias is unique and valid.",
        )

    return {
        "type": "status",
        "title": "Saved Command Added",
        "data": {
            "alias": result["alias"],
            "command_template": result["command_template"],
            "hint": result["hint"],
            "uuid": result["uuid"][:8],
        },
    }


@command("user.saved-commands.modify", interactive=True)
def saved_commands_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user saved-commands modify <alias> [--command TEMPLATE] [--hint HINT] [--alias NEW_ALIAS]

    Modify an existing saved command.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing alias.",
            "Usage: !user saved-commands modify <alias> [--command ...] [--hint ...]",
        )
    alias = remaining[0]
    command_template = flags.get("command")
    hint = flags.get("hint")
    new_alias = flags.get("alias")

    svc: UserCommandsService = get_user_commands_service()
    try:
        result = svc.update(alias, command_template=command_template, hint=hint, new_alias=new_alias)
    except UserCommandsError as e:
        raise CommandValidationError(str(e))
    except Exception as e:
        raise CommandValidationError(
            f"Failed to modify saved command: {e}",
        )

    if not result:
        raise CommandValidationError(f"Saved command not found: '{alias}'")

    return {
        "type": "status",
        "title": "Saved Command Modified",
        "data": {
            "alias": result["alias"],
            "command_template": result["command_template"],
            "hint": result["hint"],
        },
    }


@command("user.saved-commands.delete", permission_level=PermissionLevel.DESTRUCTIVE, interactive=True)
def saved_commands_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!user saved-commands delete <alias> [alias...]

    Delete one or more saved commands by alias.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing alias(es).",
            "Usage: !user saved-commands delete <alias> [alias...]",
        )

    svc: UserCommandsService = get_user_commands_service()
    removed = []
    not_found = []

    for alias in remaining:
        if svc.delete(alias):
            removed.append(alias)
        else:
            not_found.append(alias)

    parts = []
    if removed:
        parts.append(f"Removed: {', '.join(removed)}")
    if not_found:
        parts.append(f"Not found: {', '.join(not_found)}")

    return {
        "type": "status",
        "title": "Saved Command(s) Deleted",
        "data": {"removed": removed, "not_found": not_found},
    }
