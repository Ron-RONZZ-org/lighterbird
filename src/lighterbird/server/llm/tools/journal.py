"""LLM tools for the journal domain.

Tools:
    - ``journal.find`` -- Search journal entries by title, date, or content
    - ``journal.read`` -- Full entry by UUID
    - ``journal.create`` -- Write a new journal entry
    - ``journal.delete`` -- Delete a journal entry
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lightercore.permissions import PermissionLevel

from lighterbird.server.deps import get_journal_service
from lighterbird.server.llm.tools import llm_tool


# ── Find entries ──────────────────────────────────────────────────────────────


@llm_tool(
    name="journal.find",
    description=(
        "Search journal entries by title, date range, or content. "
        "Returns matching entries with previews (first 300 chars of body)."
    ),
    params=[
        {"name": "query", "type": "string", "description": "Search term in title or body"},
        {"name": "after_date", "type": "string", "description": "ISO date filter (e.g. '2026-01-01')"},
        {"name": "before_date", "type": "string", "description": "ISO date filter (e.g. '2026-07-17')"},
        {"name": "label", "type": "string", "description": "Filter by label name"},
        {"name": "max_results", "type": "number", "description": "Maximum results (default 20)"},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_journal_find(**kwargs: Any) -> dict:
    """Search journal entries."""
    query = kwargs.get("query", "")
    label = kwargs.get("label", "")
    after = kwargs.get("after_date", "")
    before = kwargs.get("before_date", "")
    limit = int(kwargs.get("max_results", 20))

    service = get_journal_service()
    try:
        if query:
            results = service.search("content", query, limit=limit)
        elif after or before:
            # Use list_by_date with date range
            results = service.list_by_date(
                date_from=_parse_iso(after) if after else None,
                date_to=_parse_iso(before) if before else None,
            )[:limit]
        else:
            results = service.list(limit=limit)

        filtered = []
        for e in results:
            if label and label not in (e.get("_labels") or []):
                continue
            filtered.append({
                "uuid": e.get("uuid", ""),
                "title": e.get("title", ""),
                "created_at": e.get("created_at", ""),
                "body_preview": (e.get("body") or "")[:300],
                "labels": e.get("_labels", []),
            })
            if len(filtered) >= limit:
                break

        return {"success": True, "data": filtered, "total": len(filtered)}
    except Exception as exc:
        return {"success": False, "error": f"Journal search failed: {exc}"}


def _parse_iso(value: str | None) -> str | None:
    """Normalize an ISO date string."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return value


# ── Read entry ────────────────────────────────────────────────────────────────


@llm_tool(
    name="journal.read",
    description="Get the full content of a journal entry by UUID.",
    params=[
        {"name": "uuid", "type": "string", "description": "Journal entry UUID", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_journal_read(uuid: str = "") -> dict:
    """Get full journal entry."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_journal_service()
    try:
        entry = service.get(uuid)
        if not entry:
            return {"success": False, "error": f"Journal entry not found: {uuid}"}
        entry_dict = dict(entry)
        entry_dict["_labels"] = service.get_labels(uuid) or []
        return {"success": True, "data": entry_dict}
    except Exception as exc:
        return {"success": False, "error": f"Failed to read journal entry: {exc}"}


# ── Create entry ──────────────────────────────────────────────────────────────


@llm_tool(
    name="journal.create",
    description="Write a new journal entry with title, body, and optional labels.",
    params=[
        {"name": "title", "type": "string", "description": "Entry title", "required": True},
        {"name": "body", "type": "string", "description": "Entry body content (markdown supported)", "required": True},
        {"name": "labels", "type": "string", "description": "Comma-separated labels"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_journal_create(**kwargs: Any) -> dict:
    """Create a new journal entry."""
    title = kwargs.get("title", "")
    body = kwargs.get("body", "")
    if not title:
        return {"success": False, "error": "title is required"}
    if not body:
        return {"success": False, "error": "body is required"}

    data: dict[str, Any] = {
        "title": title,
        "body": body,
    }

    labels_str = kwargs.get("labels", "")
    labels = [l.strip() for l in labels_str.split(",") if l.strip()] if labels_str else []

    service = get_journal_service()
    try:
        result = service.create(data)
        if labels:
            service.add_label(result["uuid"], labels)
        return {"success": True, "data": {"uuid": result.get("uuid", ""), "title": title}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to create journal entry: {exc}"}


# ── Delete entry ──────────────────────────────────────────────────────────────


@llm_tool(
    name="journal.delete",
    description="Delete a journal entry by UUID.",
    params=[
        {"name": "uuid", "type": "string", "description": "Journal entry UUID to delete", "required": True},
    ],
    permission_level=PermissionLevel.DESTRUCTIVE,
)
def llm_journal_delete(uuid: str = "") -> dict:
    """Delete a journal entry."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_journal_service()
    try:
        ok = service.delete(uuid)
        if not ok:
            return {"success": False, "error": f"Journal entry not found: {uuid}"}
        return {"success": True, "data": {"uuid": uuid, "deleted": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to delete journal entry: {exc}"}
