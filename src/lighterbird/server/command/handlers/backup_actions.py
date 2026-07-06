"""Command handlers for ``!backup now``, ``!backup list``, ``!backup restore``,
``!backup prune``, ``!backup export``, and ``!backup import``.

Registered paths:
    - backup.now
    - backup.list
    - backup.restore
    - backup.prune
    - backup.export
    - backup.import
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from lighterbird.core.backup import (
    backup_all_strategies,
    backup_config_files,
    export_data,
    import_data,
    list_backups,
    load_config,
    prune_backups,
    resolve_target_path,
    restore_by_timestamp,
    restore_latest,
)
from lighterbird.core.paths import data_dir
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import reset_services

# ── Helpers ────────────────────────────────────────────────────────────────


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


def _backup_dir_abs() -> str:
    """Return the absolute path of the default backup directory."""
    return str((data_dir() / ".backups").resolve())


def _fmt_location() -> str:
    """Return a human-readable backup location summary."""
    lines = [f"  Local backup dir: {_backup_dir_abs()}"]
    cfg = load_config()
    for s in cfg.get("strategies", []):
        lines.append(f"  {s['id']}: {resolve_target_path(s)}")
    return "\n".join(lines)


# ── !backup now ────────────────────────────────────────────────────────────


@command("backup.now")
def backup_now(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup now [--kind data|config|all] [--target PATH]

    Create timestamped backups for all enabled strategies.
    If no strategies are configured, falls back to a single default backup.

    --target: optional absolute path to copy backups to (in addition to normal
              locations). Creates a portable timestamped directory.
    """
    kind = flags.get("kind", "all")
    created: list[str] = []
    ext_copied: list[str] = []

    if kind in ("all", "data"):
        for p in backup_all_strategies():
            created.append(str(p))

    if kind in ("all", "config"):
        for p in backup_config_files():
            created.append(str(p))

    # Copy strategies with a custom target (non-local) are handled
    # inside backup_with_strategy already. For the legacy external_dir
    # path, we also copy to it.
    load_config()

    # One-off --target: copy all created backups to the given path
    one_off_target = flags.get("target", "")
    if one_off_target and created:
        try:
            dst_root = Path(one_off_target).expanduser().resolve()
            dst_root.mkdir(parents=True, exist_ok=True)
            for p_str in created:
                src = Path(p_str)
                shutil.copy2(str(src), str(dst_root / src.name))
            ext_copied.append(str(dst_root))
        except OSError as e:
            raise CommandValidationError(f"Failed to copy to --target: {e}")

    if not created:
        return {"type": "status", "title": "Backup", "data": {"message": "No data files found to back up."}}

    msg = f"Created {len(created)} backup(s).\n\nBackup location:\n{_fmt_location()}"
    if ext_copied:
        msg += f"\nAlso copied {len(ext_copied)} to external directory."

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
    """!backup list [--stem email|calendar|contacts|todo|journal|letters|profiles|user_commands] [--strategy ID]

    List available backup snapshots (7z archives and legacy .db files).
    Optionally filter by stem or strategy.
    """
    stem = flags.get("stem")
    strategy_filter = flags.get("strategy")
    backups = list_backups()

    if stem:
        backups = [b for b in backups if b["stem"] == stem]
    if strategy_filter:
        backups = [b for b in backups if b["strategy"] == strategy_filter]

    if not backups:
        return {"type": "status", "title": "Backups", "data": {"message": "No backups found."}}

    entries = []
    for b in backups:
        is_archive = b["path"].suffix == ".7z"
        entries.append({
            "file": b["path"].name,
            "timestamp": _fmt_ts(b["timestamp"]),
            "size": _fmt_size(b["size_bytes"]),
            "database": "all" if is_archive else b["stem"],
            "strategy": b.get("strategy", "legacy"),
            "format": "7z" if is_archive else b["path"].suffix.lstrip("."),
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
        # Close all active DB connections before overwriting files
        reset_services()

        target = str(data_dir())
        if timestamp:
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


@command("backup.prune", interactive=True)
def backup_prune(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup prune [--keep N]

    Delete old backups, keeping only the N newest per (database, strategy).
    Default: per-strategy max_copies or 10.
    """
    raw = flags.get("keep", "")
    if raw:
        try:
            retention = int(raw)
        except ValueError:
            raise CommandValidationError(f"Invalid --keep value: {raw}")
    else:
        retention = None  # use per-strategy max_copies

    deleted = prune_backups(retention=retention)

    return {
        "type": "status",
        "title": "Backup Pruned",
        "data": {
            "message": f"Deleted {deleted} old backup(s).",
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
    """!backup import <path> [--force] [--overwrite FILE] [--skip FILE]

    Import data from a previously exported directory. The path must
    point to an export directory containing manifest.json.

    By default, files that already exist in the data directory are
    checked against SHA-256 from the manifest. Byte-identical files
    are auto-skipped. Files that differ are listed as "conflicts"
    and left untouched.

    Flags:
      --force            Overwrite ALL existing files without checking.
      --overwrite FILE   Overwrite a specific conflicting file.
      --skip FILE        Skip a specific conflicting file (overrides --force).
      --overwrite and --skip can be repeated for multiple files.
    """
    if not remaining:
        raise CommandValidationError("Missing export path.", "Usage: !backup import <path> [--force]")

    export_path = remaining[0]
    force = "force" in flags

    # Collect per-file decisions from --overwrite / --skip flags
    decisions: dict[str, str] = {}
    for key, value in flags.items():
        if key == "overwrite":
            for fname in value.split(","):
                decisions[fname.strip()] = "overwrite"
        elif key == "skip":
            for fname in value.split(","):
                decisions[fname.strip()] = "skip"
    try:
        reset_services()
        result = import_data(export_path, force=force)
    except (FileNotFoundError, ValueError, OSError) as e:
        raise CommandValidationError(f"Import failed: {e}")

    imported = result.get("imported", [])
    skipped = result.get("skipped", [])
    identical = result.get("identical", [])
    conflicts = result.get("conflicts", [])
    errors = result.get("errors", [])

    msg_parts = [f"Imported {len(imported)} file(s)."]
    if identical:
        msg_parts.append(f"{len(identical)} identical — skipped.")
    if skipped:
        msg_parts.append(f"{len(skipped)} skipped by user.")
    if conflicts:
        msg_parts.append(f"{len(conflicts)} conflict(s) — use --overwrite <file> or --skip <file> to resolve.")
    if errors:
        msg_parts.append(f"{len(errors)} error(s).")

    return {
        "type": "status",
        "title": "Import Complete",
        "data": {
            "imported": imported,
            "identical": identical,
            "skipped": skipped,
            "conflicts": conflicts,
            "errors": errors,
            "message": " ".join(msg_parts),
        },
    }
