"""Command handlers for the ``!backup`` domain.

Registered paths::

    backup.now           — Create backups of all DBs + optional external copy
    backup.list          — List available backup snapshots
    backup.restore       — Restore from the latest backup
    backup.prune         — Prune old backups (keep N per stem)
    backup.config        — View or change backup settings
    backup.config.set    — Set a backup config value
    backup.export        — Export all data to a portable directory
    backup.import        — Import data from an exported directory
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lighterbird.core.backup import (
    backup_all,
    backup_config_files,
    copy_to_external,
    export_data,
    import_data,
    list_backups,
    load_config,
    prune_backups,
    restore_latest,
    save_config,
)
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command


def _fmt_size(b: int) -> str:
    """Format a byte count for human display."""
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KiB"
    return f"{b / (1024 * 1024):.1f} MiB"


def _fmt_ts(ts: str) -> str:
    """Format a backup timestamp for human display."""
    if len(ts) >= 15:
        return f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]}"
    return ts


# ── !backup now ────────────────────────────────────────────────────────────


@command("backup.now")
def backup_now(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup now [--kind data|config|all]

    Create timestamped backups of all lighterbird databases, optionally
    also config files. If an external backup directory is configured,
    copies are also pushed there.
    """
    kind = flags.get("kind", "all")
    created: list[str] = []
    ext_copied: list[str] = []

    if kind in ("all", "data"):
        for p in backup_all():
            created.append(str(p))

    if kind in ("all", "config"):
        for p in backup_config_files():
            created.append(str(p))

    # Copy to external dir if configured
    cfg = load_config()
    ext_dir = cfg.get("external_dir", "")
    if ext_dir:
        backup_files = [Path(p) for p in created]
        try:
            for dst in copy_to_external(ext_dir, backup_paths=backup_files):
                ext_copied.append(str(dst))
        except OSError as e:
            return {
                "type": "error",
                "title": "Backup Created, External Copy Failed",
                "data": {
                    "backups": created,
                    "external_error": str(e),
                },
            }

    if not created:
        return {"type": "status", "title": "Backup", "data": {"message": "No data files found to back up."}}

    msg = f"Created {len(created)} backup(s)."
    if ext_copied:
        msg += f" Also copied {len(ext_copied)} to external directory."

    return {
        "type": "status",
        "title": "Backup Complete",
        "data": {
            "message": msg,
            "backups": created,
            "external_copies": ext_copied,
        },
    }


# ── !backup list ───────────────────────────────────────────────────────────


@command("backup.list")
def backup_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup list [--stem email|calendar|contacts|todo|journal]

    List available backup snapshots. Optionally filter by database stem.
    """
    stem = flags.get("stem")
    backups = list_backups()

    if stem:
        backups = [b for b in backups if b["stem"] == stem]

    if not backups:
        return {"type": "status", "title": "Backups", "data": {"message": "No backups found."}}

    entries = []
    for b in backups:
        entries.append({
            "file": b["path"].name,
            "timestamp": _fmt_ts(b["timestamp"]),
            "size": _fmt_size(b["size_bytes"]),
            "database": b["stem"],
        })

    return {
        "type": "status",
        "title": f"Backups ({len(entries)})",
        "data": {"entries": entries},
    }


# ── !backup restore ────────────────────────────────────────────────────────


@command("backup.restore")
def backup_restore(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup restore [--timestamp PREFIX]

    Restore the latest backup of each database (default), or a specific
    timestamp snapshot.

    WARNING: This overwrites your current databases. Use with caution.
    """
    timestamp = flags.get("timestamp")

    try:
        from lighterbird.core.paths import data_dir

        target = str(data_dir())
        if timestamp:
            from lighterbird.core.backup import restore_by_timestamp

            restored = restore_by_timestamp(timestamp, target)
        else:
            restored = restore_latest(target)
    except (FileNotFoundError, LookupError, OSError) as e:
        raise CommandValidationError(str(e))

    return {
        "type": "status",
        "title": "Restore Complete",
        "data": {
            "message": f"Restored {len(restored)} file(s).",
            "files": [str(p) for p in restored],
        },
    }


# ── !backup prune ──────────────────────────────────────────────────────────


@command("backup.prune")
def backup_prune(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup prune [--keep N]

    Delete old backups, keeping only the N newest per database.
    Default: 10 (or configured retention).
    """
    raw = flags.get("keep", "")
    if raw:
        try:
            retention = int(raw)
        except ValueError:
            raise CommandValidationError(f"Invalid --keep value: {raw}")
    else:
        cfg = load_config()
        retention = cfg.get("retention", 10)

    deleted = prune_backups(retention=retention)

    return {
        "type": "status",
        "title": "Backup Pruned",
        "data": {
            "message": f"Deleted {deleted} old backup(s). Keeping {retention} per database.",
        },
    }


# ── !backup config ─────────────────────────────────────────────────────────


@command("backup.config")
def backup_config(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup config [--external-dir PATH] [--retention N] [--auto-interval N]

    Without flags: show current backup configuration.

    With flags: set the corresponding config values.
    """
    cfg = load_config()

    # Show current config
    if not flags:
        return {
            "type": "status",
            "title": "Backup Config",
            "data": {
                "external_dir": cfg.get("external_dir", "(not set)"),
                "retention": cfg.get("retention", 10),
                "auto_interval_hours": cfg.get("auto_interval_hours", 0),
            },
        }

    # Update config
    changed: list[str] = []
    if "external_dir" in flags:
        cfg["external_dir"] = flags["external_dir"]
        changed.append("external_dir")
    if "retention" in flags:
        try:
            cfg["retention"] = int(flags["retention"])
            changed.append("retention")
        except ValueError:
            raise CommandValidationError(f"Invalid --retention value: {flags['retention']}")
    if "auto_interval" in flags:
        try:
            cfg["auto_interval_hours"] = int(flags["auto_interval"])
            changed.append("auto_interval_hours")
        except ValueError:
            raise CommandValidationError(f"Invalid --auto-interval value: {flags['auto_interval']}")

    save_config(cfg)

    return {
        "type": "status",
        "title": "Backup Config Updated",
        "data": {
            "changed": changed,
            "config": cfg,
        },
    }


# ── !backup export ─────────────────────────────────────────────────────────


@command("backup.export")
def backup_export(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup export [--output PATH]

    Export all lighterbird data (DBs + config files) to a portable
    timestamped directory. The directory includes a manifest.json with
    SHA-256 checksums for integrity verification.

    If --output is omitted, the export is created in the current
    working directory.
    """
    output = flags.get("output", ".")

    try:
        export_dir = export_data(output)
    except OSError as e:
        raise CommandValidationError(f"Export failed: {e}")

    return {
        "type": "status",
        "title": "Export Complete",
        "data": {
            "path": str(export_dir),
            "message": f"Data exported to: {export_dir}",
        },
    }


# ── !backup import ─────────────────────────────────────────────────────────


@command("backup.import")
def backup_import(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup import <path> [--force]

    Import data from a previously exported directory. The path must
    point to an export directory containing manifest.json.

    By default, files that already exist in the data directory are
    skipped. Use --force to overwrite existing files.
    """
    if not remaining:
        raise CommandValidationError("Missing export path.", "Usage: !backup import <path> [--force]")

    export_path = remaining[0]
    force = "force" in flags

    try:
        result = import_data(export_path, force=force)
    except (FileNotFoundError, ValueError, OSError) as e:
        raise CommandValidationError(f"Import failed: {e}")

    return {
        "type": "status",
        "title": "Import Complete",
        "data": {
            "imported": result.get("imported", []),
            "skipped": result.get("skipped", []),
            "errors": result.get("errors", []),
            "message": (
                f"Imported {len(result.get('imported', []))} file(s), "
                f"skipped {len(result.get('skipped', []))}, "
                f"errors: {len(result.get('errors', []))}"
            ),
        },
    }
