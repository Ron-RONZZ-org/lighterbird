"""Command handlers for ``!backup config`` and its sub-commands.

Registered paths:
    - backup.config
    - backup.config.list
    - backup.config.add
    - backup.config.modify
    - backup.config.default-path
    - backup.config.delete
    - backup.config.test
"""

from __future__ import annotations

from typing import Any

from lighterbird.core.backup import (
    BackupStrategy,
    add_strategy,
    get_strategy,
    list_strategies,
    load_config,
    remove_strategy,
    resolve_target_path,
    update_strategy,
    verify_strategy_target,
)
from lighterbird.core.paths import data_dir
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command

# ── Helpers ────────────────────────────────────────────────────────────────


def _backup_dir_abs() -> str:
    """Return the absolute path of the default backup directory."""
    return str((data_dir() / ".backups").resolve())


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

    raw_interval = flags.get("interval", flags.get("schedule", "0"))
    try:
        interval_minutes = float(raw_interval)
    except ValueError:
        raise CommandValidationError(f"Invalid --interval value: {raw_interval}")

    raw_max = flags.get("max_copies", "10")
    try:
        max_copies = int(raw_max)
    except ValueError:
        raise CommandValidationError(f"Invalid --max-copies value: {raw_max}")

    if interval_minutes < 0:
        raise CommandValidationError("--interval must be >= 0")
    # Cap sub-minute intervals at 1 minute since the scheduler only checks every 60s
    if 0 < interval_minutes < 0.9:
        interval_minutes = 1.0

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
    if "interval" in flags or "schedule" in flags:
        raw = flags.get("interval", flags.get("schedule", ""))
        try:
            updates["interval_minutes"] = float(raw)
        except ValueError:
            raise CommandValidationError(f"Invalid interval value: {raw}")
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


# ── !backup config default-path ────────────────────────────────────────────


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


# ── !backup config delete ──────────────────────────────────────────────────


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
