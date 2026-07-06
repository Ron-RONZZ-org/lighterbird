"""Re-exported from lightercore -- see ``lightercore.paths``."""
from __future__ import annotations

import os
from pathlib import Path

from lightercore.paths import *  # noqa: F403

# Keep backward-compatible aliases for internal lighterbird use
from lightercore.paths import _base as _lighterbird_base  # noqa: F401

# Allowlist of base directories for safe path resolution.
# Symlinks inside these dirs are permitted; symlinks that escape them are not.
_SAFE_BASE_DIRS: list[Path] = []


def _init_safe_base_dirs() -> list[Path]:
    """Initialise the list of allowed base directories."""
    global _SAFE_BASE_DIRS
    if _SAFE_BASE_DIRS:
        return _SAFE_BASE_DIRS
    dirs: list[Path] = []
    home = Path.home()
    dirs.append(home.resolve())
    # Also allow the current working directory and its ancestors
    cwd = Path.cwd().resolve()
    dirs.append(cwd)
    # Allow data directory for attachments
    try:
        from lighterbird.core.paths import data_dir
        dirs.append(data_dir().resolve())
    except Exception:
        pass
    # Allow /tmp and /var/tmp for file imports
    for tmp in (Path("/tmp"), Path("/var/tmp")):
        if tmp.is_dir():
            dirs.append(tmp.resolve())
    # Allow LIGHTERBIRD_SAFE_DIRS env var for custom base dirs
    extra = os.environ.get("LIGHTERBIRD_SAFE_DIRS", "")
    if extra:
        for d in extra.split(":"):
            p = Path(d).resolve()
            if p.exists():
                dirs.append(p)
    _SAFE_BASE_DIRS = list(set(dirs))
    return _SAFE_BASE_DIRS


def safe_resolve_path(path_str: str) -> Path:
    """Resolve a user-supplied path with traversal protection.

    Resolves the path to an absolute path (following symlinks) and
    verifies it resides under one of the allowed base directories
    (home directory, current working directory, data directory, or
    paths in ``$LIGHTERBIRD_SAFE_DIRS``).  Rejects literal ``..``
    components as an additional defence-in-depth check.

    Args:
        path_str: Raw user-supplied file path.

    Returns:
        Resolved absolute ``Path``.

    Raises:
        ValueError: If path contains ``..`` components or resolves
            outside the allowed base directories.
        FileNotFoundError: If the resolved path does not exist.
        IsADirectoryError: If the resolved path is a directory.
    """
    raw = Path(path_str)
    if ".." in raw.parts:
        raise ValueError(
            f"Path traversal not allowed: {path_str}. "
            "Use a path without '..' components.",
        )
    resolved = raw.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"File not found: {path_str}")
    if not resolved.is_file():
        raise IsADirectoryError(f"Not a file: {path_str}")

    # Symlink-aware check: ensure the resolved path is under an allowed base
    safe_dirs = _init_safe_base_dirs()
    if not any(
        resolved == d or str(resolved).startswith(str(d) + "/")
        for d in safe_dirs
    ):
        raise ValueError(
            f"Path resolves outside allowed directories: {resolved}. "
            "Allowed: home, CWD, data dir, and $LIGHTERBIRD_SAFE_DIRS."
        )
    return resolved
