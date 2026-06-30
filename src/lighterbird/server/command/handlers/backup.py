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

import shutil
from pathlib import Path
from typing import Any

from lighterbird.core.backup import (
    BackupStrategy,
    backup_all,
    backup_all_strategies,
    backup_config_files,
    copy_to_external,
    export_data,
    import_data,
    list_backups,
    list_strategies,
    get_strategy,
    add_strategy,
    update_strategy,
    remove_strategy,
    verify_strategy_target,
    load_config,
    prune_backups,
    restore_latest,
    save_config,
    resolve_target_path,
)
from lighterbird.core.paths import data_dir
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


def _fmt_location() -> str:
    """Return a human-readable backup location summary."""
    lines = [f"  Local backup dir: {_backup_dir_abs()}"]
    cfg = load_config()
    for s in cfg.get("strategies", []):
        lines.append(f"  {s['id']}: {resolve_target_path(s)}")
    return "\n".join(lines)


def _backup_dir_abs() -> str:
    """Return the absolute path of the default backup directory."""
    return str((data_dir() / ".backups").resolve())


# ── !backup now ────────────────────────────────────────────────────────────


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
    cfg = load_config()

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
    """!backup list [--stem email|calendar|contacts|todo|journal] [--strategy ID]

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


# ── !backup config ─────────────────────────────────────────────────────────


@command("backup.config")
def backup_config(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup config

    Show backup configuration summary (number of strategies, etc.).
    """
    cfg = load_config()
    strategies = cfg.get("strategies", [])
    enabled_count = sum(1 for s in strategies if s.get("enabled", True))

    summary = (
        f"Backup strategies: {len(strategies)} configured ({enabled_count} enabled)\n"
    )
    for s in strategies:
        status = "✓" if s.get("enabled", True) else "✗"
        interval = s.get("interval_minutes", 0)
        sched_str = f"{interval} min" if interval > 0 else "on-demand"
        summary += (
            f"  {status} {s['id']:12s}  {s.get('label', ''):20s}  "
            f"max {s.get('max_copies', 10):3d}  target={resolve_target_path(s)}  "
            f"every {sched_str}\n"
        )
    summary += "\nUse !backup config list for interactive management."

    return {
        "type": "status",
        "title": "Backup Config",
        "data": {"_summary": summary},
    }


# ── !backup config list ────────────────────────────────────────────────────


@command("backup.config.list")
def backup_config_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup config list

    List backup strategies in a format suitable for the interactive
    frontend list component.  The target is resolved to an absolute path.
    """
    strategies = list_strategies()
    for s in strategies:
        s["_resolved_target"] = resolve_target_path(s)
    return {
        "type": "status",
        "title": f"Backup Strategies ({len(strategies)})",
        "data": {"strategies": strategies},
    }


# ── !backup config add ─────────────────────────────────────────────────────


@command("backup.config.add")
def backup_config_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup config add --id ID --label LABEL [--interval MINUTES] [--max-copies N] [--target PATH] [--enabled true|false]

    Add a new backup strategy.

    --interval: minutes between automatic backups (default: 0 = on-demand via !backup now)
    --max-copies: how many old backups to keep (default: 10)
    --target: "local" (default backup dir) or an absolute path
    --enabled: true (default) or false
    """
    sid = flags.get("id", "")
    if not sid:
        raise CommandValidationError(
            "Missing --id", "Usage: !backup config add --id daily --label 'Daily backups'"
        )

    label = flags.get("label", "")
    if not label:
        label = sid  # fall back to id as label

    raw_interval = flags.get("interval", "0")
    try:
        interval_minutes = int(raw_interval)
    except ValueError:
        raise CommandValidationError(f"Invalid --interval value: {raw_interval}")

    raw_max = flags.get("max_copies", "10")
    try:
        max_copies = int(raw_max)
    except ValueError:
        raise CommandValidationError(f"Invalid --max-copies value: {raw_max}")

    if interval_minutes < 0:
        raise CommandValidationError("--interval must be >= 0")

    target = flags.get("target", "local")
    enabled_raw = flags.get("enabled", "true")
    enabled = enabled_raw.lower() in ("true", "1", "yes")

    try:
        strategy = BackupStrategy(
            id=sid,
            label=label,
            interval_minutes=interval_minutes,
            max_copies=max_copies,
            target=target,
            enabled=enabled,
        )
        add_strategy(strategy)
    except ValueError as e:
        raise CommandValidationError(str(e))

    return {
        "type": "status",
        "title": "Strategy Added",
        "data": {"strategy": sid, "message": f"Added backup strategy '{sid}'."},
    }


# ── !backup config modify ──────────────────────────────────────────────────


@command("backup.config.modify")
def backup_config_modify(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup config modify <id> [--label LABEL] [--interval MINUTES] [--max-copies N] [--target PATH] [--enabled true|false]

    Modify an existing backup strategy.  All flags except the strategy
    id are optional.

    --interval: minutes between automatic backups (0 = on-demand)
    --target: "local" (default) or an absolute path

    Pass --enabled "" to toggle; use "true" or "false" explicitly.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing strategy id.", "Usage: !backup config modify daily --max-copies 5"
        )
    sid = remaining[0]

    strategy = get_strategy(sid)
    if strategy is None:
        raise CommandValidationError(f"Strategy '{sid}' not found.")

    updates: dict[str, Any] = {}
    if "label" in flags:
        updates["label"] = flags["label"]
    if "interval" in flags:
        updates["interval_minutes"] = flags["interval"]
    if "max_copies" in flags:
        updates["max_copies"] = flags["max_copies"]
    if "target" in flags:
        updates["target"] = flags["target"]
    if "enabled" in flags:
        raw = flags["enabled"]
        updates["enabled"] = raw.lower() in ("true", "1", "yes") if raw else not strategy.get("enabled", True)

    if not updates:
        raise CommandValidationError("No changes specified.", "Use --label, --interval, --max-copies, --target, or --enabled.")

    try:
        update_strategy(sid, updates)
    except ValueError as e:
        raise CommandValidationError(str(e))

    changed_keys = list(updates.keys())
    return {
        "type": "status",
        "title": "Strategy Modified",
        "data": {
            "strategy": sid,
            "changed": changed_keys,
            "message": f"Modified strategy '{sid}': {', '.join(changed_keys)}.",
        },
    }


# ── !backup config remove ──────────────────────────────────────────────────


@command("backup.config.default-path")
def backup_config_default_path(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup config default-path

    Return the absolute path of the default backup directory.
    """
    return {
        "type": "status",
        "title": "Default Backup Path",
        "data": {"path": _backup_dir_abs()},
    }


@command("backup.config.delete")
def backup_config_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup config delete <id>

    Delete a backup strategy by id.  Existing backup files tagged with
    this strategy are NOT deleted (they remain for reference).
    """
    if not remaining:
        raise CommandValidationError(
            "Missing strategy id.", "Usage: !backup config delete daily"
        )
    sid = remaining[0]

    try:
        remove_strategy(sid)
    except ValueError as e:
        raise CommandValidationError(str(e))

    return {
        "type": "status",
        "title": "Strategy Deleted",
        "data": {"strategy": sid, "message": f"Deleted backup strategy '{sid}'."},
    }


# ── !backup config test ────────────────────────────────────────────────────


@command("backup.config.test")
def backup_config_test(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!backup config test <id>

    Test a strategy's target directory by attempting to write a probe
    file.  Reports success or error.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing strategy id.", "Usage: !backup config test daily"
        )
    sid = remaining[0]

    try:
        result = verify_strategy_target(sid)
    except ValueError as e:
        raise CommandValidationError(str(e))

    if result.get("success"):
        return {"type": "status", "title": "Test Passed", "data": {"message": result["message"]}}
    else:
        return {
            "type": "error",
            "title": "Test Failed",
            "data": {"message": result.get("message", ""), "error": result.get("error", "")},
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
            decisions[value] = "overwrite"
        elif key == "skip":
            decisions[value] = "skip"

    try:
        result = import_data(export_path, force=force, decisions=decisions or None)
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
