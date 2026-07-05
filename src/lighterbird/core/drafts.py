"""Per-domain draft storage using a local JSON file.

Each draft is a dict with:
  - uuid: unique identifier
  - domain: "email" | "journal" | "todo" | "calendar-event"
  - title: short human-readable label
  - data: dict of form field values (domain-specific)
  - created_at: ISO timestamp
  - updated_at: ISO timestamp

Storage: ``data_dir() / ".drafts.json"``
"""

from __future__ import annotations

import json
import uuid as _uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lighterbird.core.paths import data_dir

_DRAFTS_FILE = ".drafts.json"

_VALID_DOMAINS = frozenset({"email", "journal", "todo", "calendar-event", "letter"})


def _drafts_path() -> Path:
    return data_dir() / _DRAFTS_FILE


def _load_all() -> list[dict[str, Any]]:
    path = _drafts_path()
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_all(drafts: list[dict[str, Any]]) -> None:
    path = _drafts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(drafts, indent=2, ensure_ascii=False), encoding="utf-8")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _next_uuid() -> str:
    return _uuid.uuid4().hex[:12]


# ── Public API ─────────────────────────────────────────────────────────────


def list_drafts(domain: str | None = None) -> list[dict[str, Any]]:
    """List all drafts, optionally filtered by domain."""
    if domain is not None and domain not in _VALID_DOMAINS:
        raise ValueError(f"Invalid domain: {domain}. Valid: {', '.join(sorted(_VALID_DOMAINS))}")
    drafts = _load_all()
    if domain:
        drafts = [d for d in drafts if d.get("domain") == domain]
    # Return newest first
    drafts.sort(key=lambda d: d.get("updated_at", ""), reverse=True)
    return drafts


def get_draft(draft_uuid: str) -> dict[str, Any] | None:
    """Get a single draft by UUID."""
    for d in _load_all():
        if d.get("uuid") == draft_uuid:
            return d
    return None


def save_draft(
    domain: str,
    title: str,
    data: dict[str, Any],
    draft_uuid: str | None = None,
) -> dict[str, Any]:
    """Save (create or update) a draft.

    If *draft_uuid* is provided, updates the existing draft.
    Otherwise creates a new one.

    Returns the saved draft.
    """
    if domain not in _VALID_DOMAINS:
        raise ValueError(f"Invalid domain: {domain}. Valid: {', '.join(sorted(_VALID_DOMAINS))}")

    drafts = _load_all()
    now = _now()

    if draft_uuid:
        for i, d in enumerate(drafts):
            if d.get("uuid") == draft_uuid:
                drafts[i] = {
                    **d,
                    "title": title,
                    "data": data,
                    "updated_at": now,
                }
                _save_all(drafts)
                return drafts[i]

    # Create new
    draft = {
        "uuid": _next_uuid(),
        "domain": domain,
        "title": title,
        "data": data,
        "created_at": now,
        "updated_at": now,
    }
    drafts.append(draft)
    _save_all(drafts)
    return draft


def delete_draft(draft_uuid: str) -> bool:
    """Delete a draft by UUID. Returns True if deleted."""
    drafts = _load_all()
    before = len(drafts)
    drafts = [d for d in drafts if d.get("uuid") != draft_uuid]
    if len(drafts) == before:
        return False
    _save_all(drafts)
    return True


def delete_drafts_by_domain(domain: str) -> int:
    """Delete all drafts for a domain. Returns count deleted."""
    if domain not in _VALID_DOMAINS:
        raise ValueError(f"Invalid domain: {domain}")
    drafts = _load_all()
    before = len(drafts)
    drafts = [d for d in drafts if d.get("domain") != domain]
    _save_all(drafts)
    return before - len(drafts)


def cleanup_old_drafts(max_age_days: int = 30) -> int:
    """Delete drafts older than *max_age_days*. Returns count deleted."""
    drafts = _load_all()
    before = len(drafts)
    cutoff = datetime.now(UTC).timestamp() - max_age_days * 86400
    drafts = [
        d for d in drafts
        if _parse_ts(d.get("updated_at", "")) > cutoff
    ]
    _save_all(drafts)
    return before - len(drafts)


def _parse_ts(ts: str) -> float:
    try:
        return datetime.fromisoformat(ts).timestamp()
    except (ValueError, TypeError):
        return 0


__all__ = [
    "cleanup_old_drafts",
    "delete_draft",
    "delete_drafts_by_domain",
    "get_draft",
    "list_drafts",
    "save_draft",
]
