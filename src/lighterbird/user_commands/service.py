"""CRUD service for user-defined saved commands.

Provides template expansion for ``$1``, ``$2``, … positional placeholders.

Follows the same pattern as ``email/services/accounts.py``.
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Any

from lighterbird.user_commands.db import get_db


class UserCommandsError(Exception):
    """Validation error in user commands — converted to UserCommandsError by handlers."""


class UserCommandsService:
    """CRUD for saved commands + template expansion."""

    def __init__(self) -> None:
        self.db = get_db()

    # ── CRUD ──────────────────────────────────────────────────────────────

    def list_all(self) -> list[dict[str, Any]]:
        """Return all saved commands, ordered by alias."""
        return list(self.db.execute(
            "SELECT * FROM saved_commands ORDER BY alias ASC"
        ))

    def get_by_alias(self, alias: str) -> dict[str, Any] | None:
        """Look up a saved command by alias (case-insensitive)."""
        return self.db.execute_one(
            "SELECT * FROM saved_commands WHERE LOWER(alias) = LOWER(?)",
            (alias,),
        )

    def get_by_uuid(self, uuid_: str) -> dict[str, Any] | None:
        """Look up a saved command by UUID prefix."""
        if len(uuid_) == 36:
            return self.db.execute_one(
                "SELECT * FROM saved_commands WHERE uuid = ?",
                (uuid_,),
            )
        rows = self.db.execute(
            "SELECT * FROM saved_commands WHERE uuid LIKE ?",
            (f"{uuid_}%",),
        )
        if len(rows) == 1:
            return rows[0]
        if len(rows) > 1:
            msg = f"Multiple saved commands match UUID prefix '{uuid_[:8]}'"
            raise UserCommandsError(msg)
        return None

    def create(
        self,
        alias: str,
        command_template: str,
        hint: str = "",
    ) -> dict[str, Any]:
        """Create a new saved command.

        Args:
            alias: Short name used to invoke the command (e.g. ``ronzz``).
            command_template: Command template WITHOUT the leading ``!``,
                e.g. ``email list --folder ron@ronzz.org/$1``.
            hint: Description shown in autocomplete / list view.

        Returns:
            The newly created row.
        """
        # Validate alias
        if not alias.strip():
            raise UserCommandsError("Alias cannot be empty.")
        if not alias.strip().isidentifier() and not alias.replace("-", "").isidentifier():
            raise UserCommandsError(
                f"Invalid alias: '{alias}'. Use letters, digits, hyphens, underscores.",
            )

        # Validate template
        if not command_template.strip():
            raise UserCommandsError("Command template cannot be empty.")
        if command_template.strip().startswith("!"):
            command_template = command_template.strip()[1:]

        # Check uniqueness
        existing = self.get_by_alias(alias)
        if existing:
            raise UserCommandsError(
                f"Aliases '{alias}' already exists.",
                f"Use `!user saved-commands modify {alias} --command ...` to update it.",
            )

        now = datetime.now(timezone.utc).isoformat()
        uuid_val = str(uuid_mod.uuid4())
        self.db.execute(
            "INSERT INTO saved_commands (uuid, alias, command_template, hint, created_at, modified_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (uuid_val, alias.strip(), command_template.strip(), hint.strip(), now, now),
        )
        return self.get_by_uuid(uuid_val)

    def update(
        self,
        alias: str,
        command_template: str | None = None,
        hint: str | None = None,
        new_alias: str | None = None,
    ) -> dict[str, Any] | None:
        """Update a saved command.

        Args:
            alias: Current alias of the command to update.
            command_template: New template (or None to keep).
            hint: New hint (or None to keep).
            new_alias: Rename the alias (or None to keep).

        Returns:
            The updated row, or None if not found.
        """
        existing = self.get_by_alias(alias)
        if not existing:
            return None

        now = datetime.now(timezone.utc).isoformat()
        updates: list[str] = []
        params: list[Any] = []

        if command_template is not None:
            if command_template.strip().startswith("!"):
                command_template = command_template.strip()[1:]
            updates.append("command_template = ?")
            params.append(command_template.strip())

        if hint is not None:
            updates.append("hint = ?")
            params.append(hint.strip())

        if new_alias is not None:
            if not new_alias.strip():
                raise UserCommandsError("New alias cannot be empty.")
            # Check uniqueness (skip self)
            conflicting = self.get_by_alias(new_alias)
            if conflicting and conflicting["uuid"] != existing["uuid"]:
                raise UserCommandsError(f"Alias '{new_alias}' already in use.")
            updates.append("alias = ?")
            params.append(new_alias.strip())

        if not updates:
            return existing

        updates.append("modified_at = ?")
        params.append(now)
        params.append(existing["uuid"])

        self.db.execute(
            f"UPDATE saved_commands SET {', '.join(updates)} WHERE uuid = ?",
            tuple(params),
        )
        return self.get_by_uuid(existing["uuid"])

    def delete(self, alias: str) -> bool:
        """Delete a saved command by alias.

        Returns:
            True if deleted, False if not found.
        """
        existing = self.get_by_alias(alias)
        if not existing:
            return False
        self.db.execute(
            "DELETE FROM saved_commands WHERE uuid = ?",
            (existing["uuid"],),
        )
        return True

    # ── Template expansion ────────────────────────────────────────────────

    @staticmethod
    def expand_template(template: str, args: list[str]) -> str:
        """Replace ``$1``, ``$2``, …, ``$N`` with positional arguments.

        Args:
            template: Command template string (e.g. ``email list --folder ron/$1``).
            args: Positional argument values from the user's invocation.

        Returns:
            Expanded command string with placeholders replaced.
        """
        result = template
        for i, arg in enumerate(args, start=1):
            result = result.replace(f"${i}", arg)
        return result

    def resolve_and_expand(self, tokens: list[str]) -> tuple[list[str], dict[str, str]] | None:
        """Check if the first token is a user alias and expand it.

        Args:
            tokens: Command tokens from the user (e.g. ``["ronzz", "INBOX"]``).

        Returns:
            ``(expanded_tokens, flags)`` if the alias was found, or ``None``.
        """
        if not tokens:
            return None
        saved = self.get_by_alias(tokens[0])
        if not saved:
            return None

        expanded_str = self.expand_template(saved["command_template"], tokens[1:])

        # Parse the expanded string into tokens + flags
        from lighterbird.server.command.parser import parse_expanded
        return parse_expanded(expanded_str)
