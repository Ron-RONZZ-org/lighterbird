"""Re-exported from lightercore -- see ``lightercore.paths``."""
from __future__ import annotations

from pathlib import Path

from lightercore.paths import *  # noqa: F403

# Keep backward-compatible aliases for internal lighterbird use
from lightercore.paths import _base as _lighterbird_base  # noqa: F401


def safe_resolve_path(path_str: str) -> Path:
    """Resolve a user-supplied path with traversal protection.

    Rejects ``..`` components and verifies the resolved path exists
    and is a regular file.

    Args:
        path_str: Raw user-supplied file path.

    Returns:
        Resolved absolute ``Path``.

    Raises:
        ValueError: If path contains ``..`` components.
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
    return resolved
