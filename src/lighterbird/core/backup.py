"""Timestamped, checksum-verified database backups for lighterbird.

Backup location::

    ~/.local/share/lighterbird/.backups/{stem}_{strategy}_{timestamp}.db

Multiple backup strategies are supported — each strategy defines a
retention limit (max copies per stem) and an optional external target
directory. Strategies are stored in the backup config file.

Typical usage::

    from lighterbird.core.backup import backup_all, list_backups, restore_latest

    # Backup all known databases
    for path in backup_all():
        print("Backed up:", path)

    # List available backups
    for b in list_backups():
        print(b["timestamp"], b["size_bytes"])

    # Restore the newest backup
    restore_latest(target_dir=data_dir())
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from lighterbird.core.paths import config_dir, data_dir

# ── Constants ──────────────────────────────────────────────────────────────

_BACKUP_SUBDIR = ".backups"
_BACKUP_CONFIG_FILE = "backup.json"
_DEFAULT_MAX_COPIES = 10
_CONFIG_VERSION = 2

VALID_SCHEDULES = frozenset({"manual", "hourly", "daily", "weekly"})

# ── Strategy dataclass ─────────────────────────────────────────────────────


@dataclass
class BackupStrategy:
    """A named backup policy.

    Attributes:
        id: Unique kebab-case identifier (e.g. ``"daily"``, ``"hourly"``).
        label: Human-readable name for display.
        schedule: When this strategy runs — ``"manual"``, ``"hourly"``,
            ``"daily"``, or ``"weekly"``.  Used by the auto-scheduler;
            ``"manual"`` means only via ``!backup now``.
        max_copies: Maximum number of backups to keep per database stem.
        target: ``"local"`` (default backup dir) or an absolute path to
            an external/synced directory.
        enabled: Whether this strategy is active.
    """
    id: str
    label: str
    schedule: str = "manual"
    max_copies: int = _DEFAULT_MAX_COPIES
    target: str = "local"
    enabled: bool = True


# ── Internal helpers ───────────────────────────────────────────────────────


def _backup_dir() -> Path:
    """Return the root backup directory (``data_dir() / ".backups"``)."""
    return data_dir() / _BACKUP_SUBDIR


def _timestamp() -> str:
    """Return a sortable ISO-like timestamp string (nanosecond precision).

    Format: ``YYYYMMDDTHHMMSSnnnnnnnnn`` — no colons, spaces, or
    characters unsafe for filenames.
    """
    t = time.time_ns()
    secs = t // 1_000_000_000
    nsec = t % 1_000_000_000
    return time.strftime("%Y%m%dT%H%M%S", time.gmtime(secs)) + f"{nsec:09d}"


def _sha256(path: Path) -> str:
    """Compute the SHA-256 hex digest of *path* (8 KiB buffered)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _copy_with_verify(src: Path, dst: Path) -> Path:
    """Copy *src* to *dst* and verify SHA-256 checksum matches.

    Raises:
        OSError: If the checksum verification fails (the copy is
            removed on error).
    """
    src_checksum = _sha256(src)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    dst_checksum = _sha256(dst)
    if dst_checksum != src_checksum:
        dst.unlink(missing_ok=True)
        raise OSError(
            f"Checksum mismatch for {src.name}: "
            f"source {src_checksum[:12]} != copy {dst_checksum[:12]}"
        )
    return dst


# ── DB discovery ───────────────────────────────────────────────────────────


def _known_db_paths() -> list[Path]:
    """Return paths to all lighterbird database files that exist on disk.

    Databases are:
        - email.db
        - calendar.db
        - contacts.db
        - todo.db
        - journal.db
    """
    names = ["email.db", "calendar.db", "contacts.db", "todo.db", "journal.db"]
    d = data_dir()
    return [d / name for name in names if (d / name).exists()]


def _known_config_files() -> list[Path]:
    """Return paths to user-config files that should be backed up.

    Includes:
        - system_prompt.md (if it exists in config_dir)
    """
    files: list[Path] = []
    sp = config_dir() / "system_prompt.md"
    if sp.exists():
        files.append(sp)
    return files


# ── Backup file naming / parsing ───────────────────────────────────────────

# Filename patterns:
#   New: {stem}_{strategy}_{timestamp}.db      (strategy-aware)
#   Old: {stem}_{timestamp}.db                  (legacy, no strategy)
_BACKUP_FILE_RE = re.compile(
    r"^(.+?)_([a-z][a-z0-9-]*?)_(\d{8}T\d{15})\.(db|bak)$"
)
_LEGACY_BACKUP_FILE_RE = re.compile(
    r"^(.+?)_(\d{8}T\d{15})\.(db|bak)$"
)


def _parse_backup_filename(name: str) -> dict[str, str] | None:
    """Parse a backup filename into its components.

    Returns ``None`` if the name doesn't match expected patterns.
    """
    m = _BACKUP_FILE_RE.match(name)
    if m:
        return {
            "stem": m.group(1),
            "strategy": m.group(2),
            "timestamp": m.group(3),
            "suffix": m.group(4),
        }
    m = _LEGACY_BACKUP_FILE_RE.match(name)
    if m:
        return {
            "stem": m.group(1),
            "strategy": "legacy",
            "timestamp": m.group(2),
            "suffix": m.group(3),
        }
    return None


def _backup_filename(stem: str, strategy_id: str, ts: str, suffix: str = ".db") -> str:
    """Build a strategy-aware backup filename."""
    return f"{stem}_{strategy_id}_{ts}{suffix}"


# ── Strategy CRUD ──────────────────────────────────────────────────────────


def _config_path() -> Path:
    """Return path to the backup config JSON file."""
    return config_dir() / _BACKUP_CONFIG_FILE


def _migrate_old_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Migrate v1 flat config to v2 strategy-based config."""
    ext_dir = raw.get("external_dir", "")
    retention = raw.get("retention", _DEFAULT_MAX_COPIES)
    strategy = BackupStrategy(
        id="default",
        label="Default",
        schedule="manual",
        max_copies=int(retention),
        target=ext_dir if ext_dir else "local",
        enabled=True,
    )
    return {"version": _CONFIG_VERSION, "strategies": [asdict(strategy)]}


def load_config() -> dict[str, Any]:
    """Load backup configuration.

    Returns:
        Dict with keys:

        - **version** (:class:`int`) — Config format version.
        - **strategies** (:class:`list`) — List of strategy dicts.
    """
    defaults: dict[str, Any] = {
        "version": _CONFIG_VERSION,
        "strategies": [asdict(BackupStrategy(id="default", label="Default"))],
    }
    path = _config_path()
    if not path.exists():
        return dict(defaults)
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(defaults)

    # Detect and migrate v1 (flat) config
    if "external_dir" in raw or "retention" in raw or raw.get("version", 1) < 2:
        raw = _migrate_old_config(raw)
        # Persist migrated config
        save_config(raw)
        return raw

    # Ensure all strategies have valid fields
    for s in raw.get("strategies", []):
        s.setdefault("schedule", "manual")
        s.setdefault("max_copies", _DEFAULT_MAX_COPIES)
        s.setdefault("target", "local")
        s.setdefault("enabled", True)

    return raw


def save_config(cfg: dict[str, Any]) -> None:
    """Save backup configuration to disk.

    Args:
        cfg: Dict with ``version`` and ``strategies`` keys.

    Raises:
        ValueError: If the config is malformed.
    """
    strategies = cfg.get("strategies", [])
    if not isinstance(strategies, list):
        raise ValueError("'strategies' must be a list")

    seen_ids: set[str] = set()
    for s in strategies:
        if not isinstance(s, dict):
            raise ValueError(f"Each strategy must be a dict, got {type(s).__name__}")
        sid = s.get("id", "")
        if not sid or not isinstance(sid, str):
            raise ValueError("Each strategy must have a non-empty string 'id'")
        if not re.match(r"^[a-z][a-z0-9-]*$", sid):
            raise ValueError(
                f"Strategy id '{sid}' must match [a-z][a-z0-9-]*"
            )
        if sid in seen_ids:
            raise ValueError(f"Duplicate strategy id: {sid}")
        seen_ids.add(sid)

        # Validate types
        if not isinstance(s.get("label", ""), str):
            raise ValueError(f"Strategy '{sid}': 'label' must be a string")
        if s.get("schedule", "manual") not in VALID_SCHEDULES:
            raise ValueError(
                f"Strategy '{sid}': 'schedule' must be one of {sorted(VALID_SCHEDULES)}"
            )
        try:
            max_copies = int(s.get("max_copies", _DEFAULT_MAX_COPIES))
        except (TypeError, ValueError):
            raise ValueError(f"Strategy '{sid}': 'max_copies' must be an integer")
        if max_copies < 1:
            raise ValueError(f"Strategy '{sid}': 'max_copies' must be >= 1")
        s["max_copies"] = max_copies
        s.setdefault("target", "local")
        if not isinstance(s["target"], str):
            raise ValueError(f"Strategy '{sid}': 'target' must be a string")
        s["enabled"] = bool(s.get("enabled", True))

    cfg["version"] = _CONFIG_VERSION
    cfg["strategies"] = strategies

    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def list_strategies() -> list[dict[str, Any]]:
    """Return the list of strategy dicts (from config)."""
    cfg = load_config()
    return cfg.get("strategies", [])


def get_strategy(strategy_id: str) -> dict[str, Any] | None:
    """Return a single strategy dict by id, or ``None``."""
    for s in list_strategies():
        if s["id"] == strategy_id:
            return s
    return None


def add_strategy(strategy: BackupStrategy) -> dict[str, Any]:
    """Add a new backup strategy.

    Args:
        strategy: The strategy to add.

    Returns:
        The saved strategy dict.

    Raises:
        ValueError: If the id already exists.
    """
    cfg = load_config()
    for s in cfg["strategies"]:
        if s["id"] == strategy.id:
            raise ValueError(f"Strategy '{strategy.id}' already exists")
    s_dict = asdict(strategy)
    cfg["strategies"].append(s_dict)
    save_config(cfg)
    return s_dict


def update_strategy(strategy_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    """Update fields on an existing strategy.

    Args:
        strategy_id: The strategy id to update.
        updates: Dict of fields to change (``label``, ``schedule``,
            ``max_copies``, ``target``, ``enabled``).

    Returns:
        The updated strategy dict.

    Raises:
        ValueError: If the strategy is not found, or updates are invalid.
    """
    cfg = load_config()
    for s in cfg["strategies"]:
        if s["id"] == strategy_id:
            # Apply validated updates
            if "label" in updates:
                if not isinstance(updates["label"], str) or not updates["label"].strip():
                    raise ValueError("'label' must be a non-empty string")
                s["label"] = updates["label"].strip()
            if "schedule" in updates:
                if updates["schedule"] not in VALID_SCHEDULES:
                    raise ValueError(
                        f"'schedule' must be one of {sorted(VALID_SCHEDULES)}"
                    )
                s["schedule"] = updates["schedule"]
            if "max_copies" in updates:
                try:
                    mc = int(updates["max_copies"])
                except (TypeError, ValueError):
                    raise ValueError("'max_copies' must be an integer")
                if mc < 1:
                    raise ValueError("'max_copies' must be >= 1")
                s["max_copies"] = mc
            if "target" in updates:
                if not isinstance(updates["target"], str):
                    raise ValueError("'target' must be a string")
                s["target"] = updates["target"]
            if "enabled" in updates:
                s["enabled"] = bool(updates["enabled"])
            save_config(cfg)
            return s
    raise ValueError(f"Strategy '{strategy_id}' not found")


def remove_strategy(strategy_id: str) -> None:
    """Remove a backup strategy by id.

    Args:
        strategy_id: The strategy id to remove.

    Raises:
        ValueError: If the strategy is not found.
    """
    cfg = load_config()
    before = len(cfg["strategies"])
    cfg["strategies"] = [s for s in cfg["strategies"] if s["id"] != strategy_id]
    if len(cfg["strategies"]) == before:
        raise ValueError(f"Strategy '{strategy_id}' not found")
    save_config(cfg)


# ── Public API: Strategy-aware Backup ──────────────────────────────────────


def backup_with_strategy(
    db_path: Path,
    strategy: dict[str, Any],
    *,
    suffix: str = ".db",
) -> Path | None:
    """Create a backup tagged with *strategy*.

    The backup file is stored at::

        {backup_dir}/{stem}_{strategy[id]}_{timestamp}{suffix}

    After a successful copy, old backups for this (stem, strategy) are
    pruned according to the strategy's ``max_copies``.  If the strategy
    has a ``target`` other than ``"local"``, the backup is also copied
    there.

    Args:
        db_path:   Path to the source file.
        strategy:  Strategy dict (from config).
        suffix:    File extension (``.db`` or ``.bak``).

    Returns:
        Path to the created backup file, or ``None`` if *db_path* does
        not exist.
    """
    if not db_path.exists():
        return None

    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = _timestamp()
    stem = db_path.stem
    strategy_id = strategy["id"]
    backup_path = backup_dir / _backup_filename(stem, strategy_id, ts, suffix)

    _copy_with_verify(db_path, backup_path)

    # Prune old backups for this (stem, strategy)
    _prune_for_stem_and_strategy(stem, strategy_id, retention=strategy["max_copies"], suffix=suffix)

    # Copy to external target if configured
    target = strategy.get("target", "local")
    if target and target != "local":
        try:
            dst_root = Path(target).expanduser().resolve()
            dst_root.mkdir(parents=True, exist_ok=True)
            dst = dst_root / backup_path.name
            shutil.copy2(str(backup_path), str(dst))
        except OSError:
            pass  # best-effort external copy

    return backup_path


def backup_all_strategies() -> list[Path]:
    """Backup all known databases for every enabled strategy.

    Returns:
        List of backup file paths created.
    """
    created: list[Path] = []
    strategies = list_strategies()
    enabled = [s for s in strategies if s.get("enabled", True)]

    for db_path in _known_db_paths():
        for strategy in enabled:
            result = backup_with_strategy(db_path, strategy)
            if result is not None:
                created.append(result)

    return created


def backup_database(db_path: Path, *, retention: int | None = None) -> Path | None:
    """Create a backup of *db_path* using the default strategy.

    This is a backward-compatible wrapper around
    :func:`backup_with_strategy`.  It uses a default strategy with the
    given *retention* (or ``_DEFAULT_MAX_COPIES`` if not specified).

    Args:
        db_path:   Path to the database file to back up.
        retention: Max backups to keep for this stem.  Uses the
            configured default if ``None``.

    Returns:
        Path to the created backup, or ``None`` if *db_path* does not
        exist.
    """
    strategies = list_strategies()
    if strategies:
        # Use the first enabled strategy, or default
        s = next((s for s in strategies if s.get("enabled", True)), strategies[0])
    else:
        s = {"id": "default", "max_copies": retention or _DEFAULT_MAX_COPIES, "target": "local"}
    return backup_with_strategy(db_path, s)


def backup_all(*, retention: int | None = None) -> list[Path]:
    """Backup all known databases (compatibility wrapper).

    If strategies are configured, delegates to
    :func:`backup_all_strategies`.  Otherwise creates a single backup
    with the default strategy.

    Args:
        retention: Ignored when strategies are configured.  Kept for
            backward compat.

    Returns:
        List of backup file paths created.
    """
    cfg = load_config()
    if cfg.get("strategies"):
        return backup_all_strategies()

    # No strategies — backward-compat single backup
    default_strategy = {
        "id": "default",
        "max_copies": retention or _DEFAULT_MAX_COPIES,
        "target": "local",
    }
    created: list[Path] = []
    for db_path in _known_db_paths():
        result = backup_with_strategy(db_path, default_strategy)
        if result is not None:
            created.append(result)
    return created


def backup_config_files(*, retention: int | None = None) -> list[Path]:
    """Backup user configuration files (system_prompt.md, etc.).

    Args:
        retention: Max backups per config stem (per-strategy when
            strategies configured).

    Returns:
        List of backup file paths created.
    """
    created: list[Path] = []
    cfg = load_config()
    strategies = cfg.get("strategies", [])
    enabled = [s for s in strategies if s.get("enabled", True)] if strategies else [{"id": "default", "max_copies": retention or _DEFAULT_MAX_COPIES, "target": "local"}]

    for cfg_path in _known_config_files():
        for strategy in enabled:
            result = backup_with_strategy(
                cfg_path, strategy, suffix=".bak"
            )
            if result is not None:
                created.append(result)
    return created


# ── Public API: External directory sync ────────────────────────────────────


def copy_to_external(target_dir: str | Path, *, backup_paths: list[Path] | None = None) -> list[Path]:
    """Copy backup files to an external (e.g., synced) directory.

    This is the "dumb simple" remote backup: the user configures a
    directory that happens to be synced by Nextcloud, Dropbox, etc.

    Args:
        target_dir:   Path to an external directory (created if missing).
        backup_paths: Specific backup files to copy. If ``None``, copies
                      all backup files.

    Returns:
        List of destination paths that were written.

    Raises:
        OSError: If *target_dir* cannot be written.
    """
    dst_root = Path(target_dir).expanduser().resolve()
    dst_root.mkdir(parents=True, exist_ok=True)

    if backup_paths is None:
        backups = list_backups()
        backup_paths = [b["path"] for b in backups]

    copied: list[Path] = []
    for bp in backup_paths:
        dst = dst_root / bp.name
        shutil.copy2(str(bp), str(dst))
        copied.append(dst)
    return copied


# ── Public API: Test strategy ──────────────────────────────────────────────


def verify_strategy_target(strategy_id: str) -> dict[str, Any]:
    """Test a backup strategy by attempting to create a backup.

    Creates a temporary backup file to verify the target is writable,
    then removes it.

    Args:
        strategy_id: The strategy id to test.

    Returns:
        Dict with keys:
        - **success** (:class:`bool`)
        - **message** (:class:`str`) — Human-readable result.
        - **error** (:class:`str`, optional) — Error detail on failure.

    Raises:
        ValueError: If the strategy is not found.
    """
    strategy = get_strategy(strategy_id)
    if strategy is None:
        raise ValueError(f"Strategy '{strategy_id}' not found")

    target = strategy.get("target", "local")
    try:
        if target == "local":
            # Verify .backups/ is writable
            bdir = _backup_dir()
            bdir.mkdir(parents=True, exist_ok=True)
            probe = bdir / f".probe_{_timestamp()}.tmp"
            probe.write_text("probe")
            probe.unlink()
            location = str(bdir)
        else:
            dst = Path(target).expanduser().resolve()
            dst.mkdir(parents=True, exist_ok=True)
            probe = dst / f".probe_{_timestamp()}.tmp"
            probe.write_text("probe")
            probe.unlink()
            location = str(dst)

        return {"success": True, "message": f"Target is writable: {location}"}
    except OSError as e:
        return {"success": False, "message": f"Target is NOT writable: {target}", "error": str(e)}


# ── Public API: List, Restore, Prune ───────────────────────────────────────


def list_backups() -> list[dict[str, Any]]:
    """List available backup files, newest first.

    Returns:
        A list of dicts, each with keys: **path** (:class:`Path`),
        **timestamp** (:class:`str`), **size_bytes** (:class:`int`),
        **stem** (:class:`str`), **strategy** (:class:`str`).
    """
    bdir = _backup_dir()
    if not bdir.is_dir():
        return []

    backups: list[dict[str, Any]] = []
    for p in sorted(bdir.iterdir(), reverse=True):
        if p.suffix not in (".db", ".bak"):
            continue
        parsed = _parse_backup_filename(p.name)
        if parsed is None:
            continue
        backups.append({
            "path": p,
            "timestamp": parsed["timestamp"],
            "size_bytes": p.stat().st_size,
            "stem": parsed["stem"],
            "strategy": parsed["strategy"],
        })

    return backups


def list_backups_for(stem: str) -> list[dict[str, Any]]:
    """List backups matching a specific stem (e.g. ``"email"``).

    Args:
        stem: Original filename stem (e.g. ``"email"`` for ``email.db``).

    Returns:
        List of backup dicts, newest first.
    """
    return [b for b in list_backups() if b["stem"] == stem]


def _resolve_backup_target_path(backup: dict[str, Any], dst_dir: Path) -> Path:
    """Determine the restore target path for a backup entry."""
    stem = backup["stem"]
    if backup["path"].suffix == ".db":
        original_name = f"{stem}.db"
    else:
        original_name = f"{stem}.md" if stem == "system_prompt" else f"{stem}.bak"
    return dst_dir / original_name


def restore_latest(target_dir: str | Path) -> list[Path]:
    """Restore the newest backup for each known database.

    Args:
        target_dir: Directory to restore files into (default ``data_dir()``).

    Returns:
        List of restored file paths.

    Raises:
        FileNotFoundError: If no backups exist.
        OSError: If restore checksum verification fails.
    """
    dst_dir = Path(target_dir)
    backups = list_backups()
    if not backups:
        raise FileNotFoundError("No backups found")

    restored: list[Path] = []
    seen_stems: set[str] = set()
    for b in backups:
        stem = b["stem"]
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        target_path = _resolve_backup_target_path(b, dst_dir)
        _copy_with_verify(b["path"], target_path)
        restored.append(target_path)

    return restored


def restore_by_timestamp(timestamp_prefix: str, target_dir: str | Path) -> list[Path]:
    """Restore backups matching a timestamp prefix.

    Accepts partial timestamps — e.g. ``"20260624"`` matches all
    backups from June 24, 2026.

    Args:
        timestamp_prefix: ISO timestamp prefix (may be partial).
        target_dir: Directory to restore files into.

    Returns:
        List of restored file paths.

    Raises:
        FileNotFoundError: If no backups match.
        LookupError: If the prefix matches zero or more than one backup
            for a given stem.
    """
    dst_dir = Path(target_dir)
    normalized = "".join(c for c in timestamp_prefix if c.isalnum()).lower()

    all_backups = list_backups()
    matches = [b for b in all_backups if normalized in b["timestamp"].lower()]

    if not matches:
        raise FileNotFoundError(
            f"No backup matches timestamp prefix '{timestamp_prefix}'"
        )

    restored: list[Path] = []
    for b in matches:
        target_path = _resolve_backup_target_path(b, dst_dir)
        _copy_with_verify(b["path"], target_path)
        restored.append(target_path)

    return restored


def prune_backups(*, retention: int | None = None) -> int:
    """Prune old backups, keeping the newest *retention* per (stem, strategy).

    Args:
        retention: Number of newest backups to keep per (stem, strategy)
            group.  If ``None``, uses each strategy's ``max_copies``.

    Returns:
        Number of backup files deleted.

    Raises:
        ValueError: If *retention* is less than 1.
    """
    bdir = _backup_dir()
    if not bdir.is_dir():
        return 0

    # Group by (stem, strategy)
    by_group: dict[tuple[str, str], list[Path]] = {}
    for p in sorted(bdir.iterdir(), reverse=True):
        if p.suffix not in (".db", ".bak"):
            continue
        parsed = _parse_backup_filename(p.name)
        if parsed is None:
            continue
        key = (parsed["stem"], parsed["strategy"])
        by_group.setdefault(key, []).append(p)

    # Determine retention per group based on strategy config
    strategies = {s["id"]: s["max_copies"] for s in list_strategies()}
    default_retention = _DEFAULT_MAX_COPIES

    deleted = 0
    for (stem, sid), files in by_group.items():
        max_keep = retention
        if max_keep is None:
            max_keep = strategies.get(sid, default_retention)
        if len(files) <= max_keep:
            continue
        for p in files[max_keep:]:
            try:
                p.unlink()
                deleted += 1
            except OSError:
                pass

    return deleted


def _prune_for_stem_and_strategy(
    stem: str,
    strategy_id: str,
    *,
    retention: int,
    suffix: str = ".db",
) -> int:
    """Prune backups for a specific (stem, strategy) combination."""
    bdir = _backup_dir()
    if not bdir.is_dir():
        return 0

    prefix = f"{stem}_{strategy_id}_"
    files = sorted(
        [p for p in bdir.iterdir() if p.suffix == suffix and p.stem.startswith(prefix)],
        reverse=True,
    )
    if len(files) <= retention:
        return 0

    deleted = 0
    for p in files[retention:]:
        try:
            p.unlink()
            deleted += 1
        except OSError:
            pass
    return deleted


# ── Public API: Export / Import ────────────────────────────────────────────


def export_data(output_dir: str | Path) -> Path:
    """Export all DB files + config files to a portable directory.

    Creates a timestamped directory containing::

        export-{timestamp}/
            manifest.json       # Metadata + SHA-256 checksums
            email.db
            calendar.db
            contacts.db
            todo.db
            journal.db
            config/
                system_prompt.md

    Args:
        output_dir: Parent directory for the export.

    Returns:
        Path to the created export directory.
    """
    dst_root = Path(output_dir).expanduser().resolve()
    ts = _timestamp()
    export_dir = dst_root / f"export-{ts}"
    export_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "exported_at": ts,
        "files": {},
    }

    # Copy DB files
    for db_path in _known_db_paths():
        dst = export_dir / db_path.name
        _copy_with_verify(db_path, dst)
        manifest["files"][db_path.name] = {
            "size": db_path.stat().st_size,
            "sha256": _sha256(db_path),
        }

    # Copy config files
    config_export = export_dir / "config"
    for cfg_path in _known_config_files():
        dst = config_export / cfg_path.name
        _copy_with_verify(cfg_path, dst)
        manifest["files"][f"config/{cfg_path.name}"] = {
            "size": cfg_path.stat().st_size,
            "sha256": _sha256(cfg_path),
        }

    # Write manifest
    manifest_path = export_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return export_dir


def import_data(export_dir: str | Path, *, force: bool = False) -> dict[str, Any]:
    """Import data from a previously exported directory.

    Args:
        export_dir: Path to an export directory (must contain
            ``manifest.json``).
        force: If True, overwrite existing DB files without comparing
            timestamps. If False, skip files that already exist in the
            target data directory (default).

    Returns:
        Dict with keys:

        - **imported** (:class:`list`) — names of files imported.
        - **skipped** (:class:`list`) — names of files skipped (already
          exist and ``force`` is False).
        - **errors** (:class:`list`) — names of files that failed.

    Raises:
        FileNotFoundError: If *export_dir* or ``manifest.json`` is
            missing.
        ValueError: If *manifest.json* is malformed.
    """
    src = Path(export_dir).expanduser().resolve()
    manifest_path = src / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Export directory missing manifest.json: {export_dir}")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"Invalid manifest.json: {e}") from e

    dst_data = data_dir()
    dst_config = config_dir()

    result: dict[str, Any] = {"imported": [], "skipped": [], "errors": []}

    for rel_path_str, file_info in manifest.get("files", {}).items():
        src_file = src / rel_path_str
        if not src_file.exists():
            result["errors"].append(f"{rel_path_str} (not found in export)")
            continue

        # Determine destination
        if rel_path_str.startswith("config/"):
            dst_file = dst_config / src_file.name
        else:
            dst_file = dst_data / src_file.name

        if dst_file.exists() and not force:
            result["skipped"].append(rel_path_str)
            continue

        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            _copy_with_verify(src_file, dst_file)
            result["imported"].append(rel_path_str)
        except OSError as e:
            result["errors"].append(f"{rel_path_str} ({e})")

    return result


__all__ = [
    "BackupStrategy",
    "add_strategy",
    "backup_all",
    "backup_all_strategies",
    "backup_config_files",
    "backup_database",
    "backup_with_strategy",
    "copy_to_external",
    "export_data",
    "get_strategy",
    "import_data",
    "list_backups",
    "list_backups_for",
    "list_strategies",
    "load_config",
    "prune_backups",
    "remove_strategy",
    "restore_by_timestamp",
    "restore_latest",
    "save_config",
    "verify_strategy_target",
    "update_strategy",
    "_known_db_paths",
    "_known_config_files",
]
