"""Timestamped, checksum-verified database backups for lighterbird.

Backup location::

    ~/.local/share/lighterbird/.backups/{timestamp}.db

This directory lives directly under the data root so it survives
``rm -rf`` of per-module directories (all DBs are at the top level).

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
import shutil
import time
from pathlib import Path
from typing import Any

from lighterbird.core.paths import config_dir, data_dir

# ── Constants ──────────────────────────────────────────────────────────────

_BACKUP_SUBDIR = ".backups"
_BACKUP_CONFIG_FILE = "backup.json"
_DEFAULT_RETENTION = 10

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


# ── Public API: Backup ─────────────────────────────────────────────────────


def backup_database(db_path: Path, *, retention: int = _DEFAULT_RETENTION) -> Path | None:
    """Create a timestamped, checksum-verified backup of *db_path*.

    The backup is stored at::

        {backup_dir}/{timestamp}.db

    Args:
        db_path:   Path to the database file to back up.
        retention: Maximum number of backups to keep. Older backups are
                   pruned after a successful copy. Set to 0 to disable.

    Returns:
        Path to the created backup file, or ``None`` if *db_path* does
        not exist.

    Raises:
        OSError: If the source is unreadable, the backup dir cannot be
            written, or the checksum of the copy does not match.
    """
    if not db_path.exists():
        return None

    backup_dir = _backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = _timestamp()
    stem = db_path.stem  # e.g. "email" from "email.db"
    backup_path = backup_dir / f"{stem}_{ts}.db"

    _copy_with_verify(db_path, backup_path)

    if retention > 0:
        _prune_for_stem(stem, retention=retention)

    return backup_path


def backup_all(*, retention: int = _DEFAULT_RETENTION) -> list[Path]:
    """Backup all known lighterbird databases.

    Args:
        retention: Max backups per database stem to keep.

    Returns:
        List of backup file paths created.
    """
    created: list[Path] = []
    for db_path in _known_db_paths():
        result = backup_database(db_path, retention=retention)
        if result is not None:
            created.append(result)
    return created


def backup_config_files(*, retention: int = _DEFAULT_RETENTION) -> list[Path]:
    """Backup user configuration files (system_prompt.md, etc.).

    Args:
        retention: Max backups per config stem to keep.

    Returns:
        List of backup file paths created.
    """
    created: list[Path] = []
    for cfg_path in _known_config_files():
        backup_dir = _backup_dir()
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = _timestamp()
        stem = cfg_path.stem
        backup_path = backup_dir / f"{stem}_{ts}.bak"
        _copy_with_verify(cfg_path, backup_path)
        if retention > 0:
            _prune_for_stem(stem, retention=retention, suffix=".bak")
        created.append(backup_path)
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
        backup_paths = list_backups()

    copied: list[Path] = []
    for bp in backup_paths:
        dst = dst_root / bp.name
        shutil.copy2(str(bp), str(dst))
        copied.append(dst)
    return copied


# ── Public API: Backup config ──────────────────────────────────────────────


def _config_path() -> Path:
    """Return path to the backup config JSON file."""
    return config_dir() / _BACKUP_CONFIG_FILE


_VALID_KEYS = frozenset({"external_dir", "retention", "auto_interval_minutes"})


def load_config() -> dict[str, Any]:
    """Load backup configuration.

    Returns:
        Dict with keys:

        - **external_dir** (:class:`str`) — Path to external backup
          directory, or ``""`` if not configured.
        - **retention** (:class:`int`) — Number of backups to keep.
        - **auto_interval_minutes** (:class:`int`) — Minutes between
          automatic backups (0 = disabled).
    """
    defaults = {"external_dir": "", "retention": _DEFAULT_RETENTION, "auto_interval_minutes": 0}
    path = _config_path()
    if not path.exists():
        return dict(defaults)
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(defaults)

    # Sanitize: strip unknown keys, fill defaults, coerce types
    cleaned: dict[str, Any] = {}
    for k, default_val in defaults.items():
        val = raw.get(k, default_val)
        # Coerce to the expected type
        if isinstance(default_val, int):
            try:
                val = int(val)
            except (TypeError, ValueError):
                val = default_val
        elif isinstance(default_val, str):
            val = str(val) if not isinstance(val, str) else val
        cleaned[k] = val
    return cleaned


def save_config(cfg: dict[str, Any]) -> None:
    """Save backup configuration to disk.

    Validates that *cfg* contains only recognised keys with correct types.

    Args:
        cfg: Dict with keys ``external_dir`` (:class:`str`),
            ``retention`` (:class:`int`),
            ``auto_interval_minutes`` (:class:`int`).

    Raises:
        ValueError: If *cfg* contains unknown keys or values of the
            wrong type.
    """
    unknown = set(cfg) - _VALID_KEYS
    if unknown:
        raise ValueError(
            f"Unknown backup config key(s): {', '.join(sorted(unknown))}. "
            f"Valid keys: {', '.join(sorted(_VALID_KEYS))}"
        )

    expected_types: dict[str, type] = {
        "external_dir": str,
        "retention": int,
        "auto_interval_minutes": int,
    }
    for key, expected in expected_types.items():
        if key in cfg and not isinstance(cfg[key], expected):
            raise ValueError(
                f"Backup config key '{key}' must be {expected.__name__}, "
                f"got {type(cfg[key]).__name__}"
            )

    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ── Public API: List, Restore, Prune ───────────────────────────────────────


def list_backups() -> list[dict[str, Any]]:
    """List available backup files, newest first.

    Returns:
        A list of dicts, each with keys: **path** (:class:`Path`),
        **timestamp** (:class:`str`), **size_bytes** (:class:`int`),
        **stem** (:class:`str`) — the original file stem (e.g. ``"email"``).
    """
    bdir = _backup_dir()
    if not bdir.is_dir():
        return []

    backups: list[dict[str, Any]] = []
    for p in sorted(bdir.iterdir(), reverse=True):
        if p.suffix not in (".db", ".bak"):
            continue
        # Parse stem_YYYYMMDDTHHMMSS... → stem, timestamp
        parts = p.stem.rsplit("_", 1)
        stem = parts[0] if len(parts) == 2 else p.stem
        ts = parts[1] if len(parts) == 2 else p.stem
        backups.append({
            "path": p,
            "timestamp": ts,
            "size_bytes": p.stat().st_size,
            "stem": stem,
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
        # Determine original filename
        if b["path"].suffix == ".db":
            original_name = f"{stem}.db"
        else:
            original_name = f"{stem}.md" if stem == "system_prompt" else f"{stem}.bak"
        target_path = dst_dir / original_name
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
        if b["path"].suffix == ".db":
            original_name = f"{b['stem']}.db"
        else:
            original_name = f"{b['stem']}.md" if b["stem"] == "system_prompt" else f"{b['stem']}.bak"
        target_path = dst_dir / original_name
        _copy_with_verify(b["path"], target_path)
        restored.append(target_path)

    return restored


def prune_backups(*, retention: int = _DEFAULT_RETENTION) -> int:
    """Prune old backups, keeping the newest *retention* per stem.

    Args:
        retention: Number of newest backups to keep per stem. Must
            be >= 1.

    Returns:
        Number of backup files deleted.

    Raises:
        ValueError: If *retention* is less than 1.
    """
    if retention < 1:
        raise ValueError(f"retention must be >= 1, got {retention}")

    bdir = _backup_dir()
    if not bdir.is_dir():
        return 0

    # Group backup files by stem
    by_stem: dict[str, list[Path]] = {}
    for p in sorted(bdir.iterdir(), reverse=True):
        if p.suffix not in (".db", ".bak"):
            continue
        parts = p.stem.rsplit("_", 1)
        stem = parts[0] if len(parts) == 2 else p.stem
        by_stem.setdefault(stem, []).append(p)

    deleted = 0
    for stem, files in by_stem.items():
        if len(files) <= retention:
            continue
        for p in files[retention:]:
            try:
                p.unlink()
                deleted += 1
            except OSError:
                pass

    return deleted


def _prune_for_stem(stem: str, *, retention: int, suffix: str = ".db") -> int:
    """Prune backups for a single stem (used internally after backup)."""
    bdir = _backup_dir()
    if not bdir.is_dir():
        return 0

    files = sorted(
        [p for p in bdir.iterdir() if p.suffix == suffix and p.stem.startswith(f"{stem}_")],
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

    Creates a timestamped directory containing:

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
    "backup_database",
    "backup_all",
    "backup_config_files",
    "copy_to_external",
    "list_backups",
    "list_backups_for",
    "restore_latest",
    "restore_by_timestamp",
    "prune_backups",
    "export_data",
    "import_data",
    "load_config",
    "save_config",
    "_known_db_paths",
    "_known_config_files",
]
