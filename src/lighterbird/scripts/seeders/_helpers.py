"""Shared helper functions for the seed sub-package."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path


def _parse_dot_dev(dot_dev_path: str | Path | None) -> dict[str, str]:
    """Parse the ``.dev`` file into a dict of key→value."""
    result: dict[str, str] = {}
    if dot_dev_path is None:
        candidate = Path(__file__).resolve().parent.parent.parent.parent.parent / ".dev"
        if not candidate.exists():
            return result
        dot_dev_path = candidate

    path = Path(dot_dev_path)
    if not path.exists():
        return result

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _ts(days_ago: int = 0, hours_ago: int = 0) -> str:
    """Return an ISO timestamp offset from now."""
    dt = datetime.now(UTC) - timedelta(days=days_ago, hours=hours_ago)
    return dt.isoformat()


def _gen_uuid() -> str:
    return str(uuid.uuid4())
