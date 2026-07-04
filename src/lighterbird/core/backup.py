"""Re-exported from lightercore -- see ``lightercore.backup``.

Keeps backward-compatible aliases for lighterbird-specific internal APIs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lightercore.backup import *  # noqa: F401, F403

# Keep backward-compatible aliases
from lightercore.backup import (  # noqa: F401
    _checkpoint_known_dbs,
    _create_strategy_archive,
    _extract_archive,
    _known_db_paths,
    _known_config_files,
    BackupStrategy,
    get_strategy,
    prune_backups,
    resolve_target_path,
)
from lightercore.backup import _backup_dir, _sha256  # noqa: F401 — private, not in __all__
from lightercore.backup import backup_database as _lightercore_backup_database

# ── Lighterbird-specific wrappers (not in lightercore) ──────────────


def backup_with_strategy(
    db_path: str | Path,
    strategy: dict[str, Any] | BackupStrategy,
    *,
    suffix: str = ".db",
) -> Path | None:
    """Backward-compat wrapper around lightercore's ``backup_database``."""
    strategy_dict = strategy.to_dict() if isinstance(strategy, BackupStrategy) else strategy
    return _lightercore_backup_database(Path(db_path), strategy=strategy_dict)


def backup_config_files(*, retention: int | None = None) -> list[Path]:
    """Backup user configuration files (Markdown config, etc.) as ``.bak``.

    Creates individual backup files for each discovered config file using
    the first enabled strategy, or a default strategy.
    """
    from lightercore.backup import _backup_dir, _timestamp, _backup_filename, _copy_with_verify

    strategies = list_strategies()
    enabled = (
        [s for s in strategies if s.get("enabled", True)]
        if strategies
        else [{"id": "default", "max_copies": retention or 10, "target": "local"}]
    )

    created: list[Path] = []
    for cfg_path in _known_config_files():
        for strat in enabled:
            ts = _timestamp()
            bdir = _backup_dir()
            fname = _backup_filename(cfg_path.stem, strat["id"], ts)
            backup_path = bdir / f"{fname}.bak"
            _copy_with_verify(cfg_path, backup_path)
            created.append(backup_path)
    return created
