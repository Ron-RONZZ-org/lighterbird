"""Command handler for the ``!reset`` domain.

Registered paths::

    reset — Reset lighterbird to a fresh state

Subcommands:

    !reset <path>          — Backup to <path> then reset
    !reset --no-backup     — Reset without backup (requires GUI confirmation)

The ``--no-backup`` mode returns a ``form-required`` response with
form type ``reset-no-backup``, which triggers a ``ConfirmDialog`` in
the frontend.  The frontend must send back a ``confirmed`` flag to
proceed.
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command


@command("reset", interactive=True, form_type="reset-no-backup")
def reset_cmd(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!reset [path] [--no-backup]

    Reset lighterbird to a fresh state.

    Parameters:
        path: Path to save a 7z backup archive before resetting.
            If a directory is given, a filename is auto-generated
            (``reset-{timestamp}.7z``).  Mutually exclusive with
            ``--no-backup``.

    Flags:
        --no-backup: Skip backup and delete everything (irreversible!).
            Requires GUI confirmation.

    If neither a path nor ``--no-backup`` is provided, an error is
    returned explaining the options.
    """
    has_path = bool(remaining)
    no_backup = "no-backup" in flags
    confirmed = flags.get("confirmed", "").lower() in ("true", "1", "yes")

    # ── Validate arguments ──────────────────────────────────────────────
    if not has_path and not no_backup:
        raise CommandValidationError(
            "You must provide either a backup path or --no-backup.",
            "Usage: !reset /path/to/backup.7z   or   !reset --no-backup",
        )

    if has_path and no_backup:
        raise CommandValidationError(
            "Cannot specify both a backup path and --no-backup.",
            "Use either !reset <path> to backup first, or !reset --no-backup to skip backup.",
        )

    # ── --no-backup mode: require GUI confirmation ──────────────────────
    if no_backup and not confirmed:
        # Return form-required to trigger ConfirmDialog in the frontend
        return {
            "type": "form-required",
            "title": "Confirm Reset",
            "data": {
                "form": "reset-no-backup",
                "message": (
                    "This will permanently delete ALL your data — "
                    "emails, contacts, todos, journal entries, calendar events, "
                    "letters, profiles, saved commands, and stored passwords. "
                    "This action CANNOT be undone."
                ),
            },
        }

    # ── Execute reset ──────────────────────────────────────────────────
    from lighterbird.core.reset import reset_to_fresh_state

    try:
        backup_path = remaining[0] if remaining else None
        result = reset_to_fresh_state(backup_path=backup_path)
    except (FileNotFoundError, OSError) as e:
        raise CommandValidationError(f"Reset failed: {e}")

    # ── Build response ─────────────────────────────────────────────────
    msg_parts = ["Lighterbird has been reset to a fresh state."]
    if result.get("backup_path"):
        msg_parts.append(f"Backup saved to: {result['backup_path']}")
    msg_parts.append(
        f"Databases removed: {len(result.get('databases_removed', []))}"
    )
    msg_parts.append(
        f"Schemas recreated: {len(result.get('schema_recreated', []))}"
    )
    msg_parts.append(
        f"Credentials cleared: {result.get('credentials_cleared', 0)}"
    )

    return {
        "type": "status",
        "title": "Reset Complete",
        "data": {
            "message": " ".join(msg_parts),
            **result,
        },
    }
