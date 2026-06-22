"""XDG-compliant path resolution for lighterbird.

Supports ``LIGHTERBIRD_DIR`` environment variable override (same pattern
as A-core's ``A_DIR``) and sentinel protection against accidental deletion.

Forked from A-core's ``A.core.paths``.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_LIGHTERBIRD_DIR_ENV = "LIGHTERBIRD_DIR"
_SENTINEL_NAME = ".lighterbird-protected"


def _base() -> Path | None:
    """Return the base directory from ``LIGHTERBIRD_DIR`` env var, or None."""
    val = os.environ.get(_LIGHTERBIRD_DIR_ENV, "").strip()
    if not val:
        return None
    return Path(val).resolve()


def data_dir() -> Path:
    """Return the lighterbird data directory.

    Default: ``~/.local/share/lighterbird``
    Override: ``LIGHTERBIRD_DIR`` → ``$LIGHTERBIRD_DIR/data``
    Also: ``LIGHTERBIRD_DATA_DIR`` env var.
    """
    override = os.environ.get("LIGHTERBIRD_DATA_DIR")
    if override:
        return Path(override)
    base = _base()
    if base is not None:
        return base / "data"
    return Path.home() / ".local" / "share" / "lighterbird"


def config_dir() -> Path:
    """Return the lighterbird config directory.

    Default: ``~/.config/lighterbird``
    """
    override = os.environ.get("LIGHTERBIRD_CONFIG_DIR")
    if override:
        return Path(override)
    base = _base()
    if base is not None:
        return base / "config"
    return Path.home() / ".config" / "lighterbird"


def cache_dir() -> Path:
    """Return the lighterbird cache directory.

    Default: ``~/.cache/lighterbird``
    """
    override = os.environ.get("LIGHTERBIRD_CACHE_DIR")
    if override:
        return Path(override)
    base = _base()
    if base is not None:
        return base / "cache"
    return Path.home() / ".cache" / "lighterbird"


def state_dir() -> Path:
    """Return the lighterbird state directory.

    Default: ``~/.local/state/lighterbird``
    """
    override = os.environ.get("LIGHTERBIRD_STATE_DIR")
    if override:
        return Path(override)
    base = _base()
    if base is not None:
        return base / "state"
    return Path.home() / ".local" / "state" / "lighterbird"


def ensure_dirs() -> None:
    """Ensure all lighterbird directories exist and are protected."""
    for d in [data_dir(), config_dir(), cache_dir(), state_dir()]:
        d.mkdir(parents=True, exist_ok=True)
        protect_directory(d)


# ── Sentinel protection ──────────────────────────────────────────────────


def protect_directory(path: Path) -> Path:
    """Create a ``.lighterbird-protected`` sentinel marker in *path*.

    The marker signals that automated tools should not delete this directory.
    Idempotent.
    """
    path.mkdir(parents=True, exist_ok=True)
    sentinel = path / _SENTINEL_NAME
    sentinel.touch(exist_ok=True)
    return path


def is_protected(path: Path) -> bool:
    """Check if *path* or any ancestor is protected."""
    for parent in [path, *path.parents]:
        if (parent / _SENTINEL_NAME).exists():
            return True
    return False


def safe_rmtree(path: Path, *, force: bool = False) -> None:
    """Remove a directory tree, refusing if protected.

    Raises:
        ProtectedPathError: If protected and ``force`` is False.
        FileNotFoundError: If path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not force and is_protected(path):
        from lighterbird.core.exceptions import ProtectedPathError

        raise ProtectedPathError(path, "delete")
    shutil.rmtree(path)


def safe_unlink(path: Path, *, force: bool = False) -> None:
    """Delete a file, refusing if parent is protected.

    Raises:
        ProtectedPathError: If protected and ``force`` is False.
        FileNotFoundError: If path does not exist.
    """
    if not path.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    if not force and is_protected(path.parent):
        from lighterbird.core.exceptions import ProtectedPathError

        raise ProtectedPathError(path, "unlink")
    path.unlink()


def protect_all() -> None:
    """Protect all standard lighterbird directories. Idempotent."""
    for d in [data_dir(), config_dir(), cache_dir(), state_dir()]:
        protect_directory(d)
