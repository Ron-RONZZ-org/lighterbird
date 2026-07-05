"""Command handlers for the ``!backup`` domain.

Registered paths::

    backup.now              — Create backups of all DBs for all strategies
    backup.list             — List available backup snapshots
    backup.restore          — Restore from the latest backup
    backup.prune            — Prune old backups (keep N per stem+strategy)
    backup.config           — View backup config summary
    backup.config.list      — List backup strategies (table)
    backup.config.add       — Add a backup strategy
    backup.config.modify    — Modify a backup strategy
    backup.config.delete    — Delete a backup strategy
    backup.config.test      — Test a strategy's target is writable
    backup.export           — Export all data to a portable directory
    backup.import           — Import data from an exported directory
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.registry import command

# Side-effect imports to register handlers split into sub-modules
from lighterbird.server.command.handlers.backup_actions import (  # noqa: F401
    backup_now,
    backup_list,
    backup_restore,
    backup_prune,
    backup_export,
    backup_import,
)
from lighterbird.server.command.handlers.backup_config import (  # noqa: F401
    backup_config,
    backup_config_list,
    backup_config_add,
    backup_config_modify,
    backup_config_default_path,
    backup_config_delete,
    backup_config_test,
)


# ── Root handler ───────────────────────────────────────────────────────────


@command("backup")
def backup_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup — Show available backup subcommands."""
    return {
        "type": "status",
        "title": "Backup Commands",
        "data": {
            "_summary": (
                "Available !backup commands:\n"
                "  !backup now [--target P] — Create 7z backup archives for all strategies\n"
                "  !backup list             — List available backup snapshots\n"
                "  !backup restore          — Restore from the latest backup\n"
                "  !backup prune            — Delete old backups, keeping N newest\n"
                "  !backup config           — View backup config summary\n"
                "  !backup config list      — List backup strategies\n"
                "  !backup config add       — Add a backup strategy\n"
                "  !backup config modify    — Modify a backup strategy\n"
                "  !backup config delete    — Delete a backup strategy\n"
                "  !backup config test      — Test a strategy's target\n"
                "  !backup config default-path — Show default backup directory path\n"
                "  !backup export           — Export all data to a portable directory\n"
                "  !backup import           — Import data (auto-skip identical; --overwrite/--skip per file)"
            ),
        },
    }
