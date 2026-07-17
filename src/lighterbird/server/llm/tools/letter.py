"""LLM tools for the letter domain.

Tools:
    - ``letter.find`` -- Search letters by title, recipient, or direction
    - ``letter.read`` -- Full letter content by UUID
    - ``letter.create`` -- Create a draft letter
    - ``letter.update`` -- Modify a draft letter
    - ``letter.delete`` -- Delete a letter
"""

from __future__ import annotations

from typing import Any

from lightercore.permissions import PermissionLevel

from lighterbird.server.deps import get_letter_service
from lighterbird.server.llm.tools import llm_tool


def _letter_preview(l: dict) -> dict:
    """Return a preview of a letter dict."""
    return {
        "uuid": l.get("uuid", ""),
        "title": l.get("title", ""),
        "recipient": l.get("recipient", ""),
        "sender": l.get("sender", ""),
        "direction": l.get("direction", ""),
        "status": l.get("status", ""),
        "created_at": l.get("created_at", ""),
        "tags": l.get("_tags", []),
    }


# ── Find letters ──────────────────────────────────────────────────────────────


@llm_tool(
    name="letter.find",
    description=(
        "Search letters by title, recipient, sender, direction (sent/received), or status. "
        "Returns matching letters with basic info."
    ),
    params=[
        {"name": "query", "type": "string", "description": "Search term in title or recipient name"},
        {"name": "direction", "type": "string", "description": "Filter by direction: 'sent' or 'received'"},
        {"name": "status", "type": "string", "description": "Filter by status: 'draft', 'sent', 'received'"},
        {"name": "tag", "type": "string", "description": "Filter by tag name"},
        {"name": "max_results", "type": "number", "description": "Maximum results (default 20)"},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_letter_find(**kwargs: Any) -> dict:
    """Search letters."""
    query = kwargs.get("query", "")
    direction = kwargs.get("direction", "")
    status = kwargs.get("status", "")
    tag = kwargs.get("tag", "")
    limit = int(kwargs.get("max_results", 20))

    service = get_letter_service()
    try:
        if query:
            results = service.search(query=query, limit=limit)
        else:
            results = service.list(limit=limit)

        filtered = []
        for l in results:
            if direction and (l.get("direction") or "") != direction:
                continue
            if status and (l.get("status") or "") != status:
                continue
            if tag and tag not in (l.get("_tags") or []):
                continue
            filtered.append(_letter_preview(l))
            if len(filtered) >= limit:
                break

        return {"success": True, "data": filtered, "total": len(filtered)}
    except Exception as exc:
        return {"success": False, "error": f"Letter search failed: {exc}"}


# ── Read letter ───────────────────────────────────────────────────────────────


@llm_tool(
    name="letter.read",
    description="Get the full content of a letter by UUID, including body, sender, recipient, and thread info.",
    params=[
        {"name": "uuid", "type": "string", "description": "Letter UUID", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_letter_read(uuid: str = "") -> dict:
    """Get full letter content."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_letter_service()
    try:
        letter = service.get(uuid)
        if not letter:
            return {"success": False, "error": f"Letter not found: {uuid}"}

        letter_dict = dict(letter)
        # Attach tags and body
        body = service.get_body(uuid)
        letter_dict["body"] = body
        letter_dict["_tags"] = service.get_tags(uuid) or []
        return {"success": True, "data": letter_dict}
    except Exception as exc:
        return {"success": False, "error": f"Failed to read letter: {exc}"}


# ── Create letter ─────────────────────────────────────────────────────────────


@llm_tool(
    name="letter.create",
    description="Create a new letter draft with recipient, sender, title, and body.",
    params=[
        {"name": "title", "type": "string", "description": "Letter title", "required": True},
        {"name": "recipient", "type": "string", "description": "Recipient name", "required": True},
        {"name": "body", "type": "string", "description": "Letter body content"},
        {"name": "sender", "type": "string", "description": "Sender name (defaults to user profile)"},
        {"name": "direction", "type": "string", "description": "Direction: 'sent' or 'received' (default 'sent')"},
        {"name": "tags", "type": "string", "description": "Comma-separated tags"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_letter_create(**kwargs: Any) -> dict:
    """Create a new letter draft."""
    title = kwargs.get("title", "")
    recipient = kwargs.get("recipient", "")
    if not title:
        return {"success": False, "error": "title is required"}
    if not recipient:
        return {"success": False, "error": "recipient is required"}

    body = kwargs.get("body", "")

    data: dict[str, Any] = {
        "title": title,
        "recipient": recipient,
        "sender": kwargs.get("sender", ""),
        "direction": kwargs.get("direction", "sent"),
        "status": "draft",
    }

    tags_str = kwargs.get("tags", "")
    tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

    service = get_letter_service()
    try:
        result = service.create(data)
        if body:
            service.store_body(result["uuid"], body)
        if tags:
            service.add_tags(result["uuid"], tags)
        return {"success": True, "data": {"uuid": result.get("uuid", ""), "title": title}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to create letter: {exc}"}


# ── Update letter ─────────────────────────────────────────────────────────────


@llm_tool(
    name="letter.update",
    description="Modify an existing letter. Only provided fields are updated.",
    params=[
        {"name": "uuid", "type": "string", "description": "Letter UUID to modify", "required": True},
        {"name": "title", "type": "string", "description": "New title"},
        {"name": "recipient", "type": "string", "description": "New recipient"},
        {"name": "body", "type": "string", "description": "New body content"},
        {"name": "sender", "type": "string", "description": "New sender"},
        {"name": "direction", "type": "string", "description": "New direction"},
        {"name": "status", "type": "string", "description": "New status"},
        {"name": "tags", "type": "string", "description": "Comma-separated tags (replaces all)"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_letter_update(**kwargs: Any) -> dict:
    """Modify a letter."""
    uuid = kwargs.get("uuid", "")
    if not uuid:
        return {"success": False, "error": "uuid is required"}

    data: dict[str, Any] = {}
    for field in ("title", "recipient", "sender", "direction", "status"):
        if kwargs.get(field) is not None:
            data[field] = kwargs[field]
    if kwargs.get("body") is not None:
        data["_body"] = kwargs["body"]
    if kwargs.get("tags") is not None:
        data["_tags"] = [t.strip() for t in kwargs["tags"].split(",") if t.strip()]

    if not data:
        return {"success": False, "error": "No fields to update"}

    service = get_letter_service()
    try:
        body = data.pop("_body", None)
        new_tags = data.pop("_tags", None)

        result = service.update(uuid, data)
        if not result:
            return {"success": False, "error": f"Letter not found: {uuid}"}
        if body is not None:
            service.store_body(uuid, body)
        if new_tags is not None:
            service.set_tags(uuid, new_tags)
        return {"success": True, "data": {"uuid": uuid, "updated": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to update letter: {exc}"}


# ── Delete letter ─────────────────────────────────────────────────────────────


@llm_tool(
    name="letter.delete",
    description="Permanently delete a letter by UUID.",
    params=[
        {"name": "uuid", "type": "string", "description": "Letter UUID to delete", "required": True},
    ],
    permission_level=PermissionLevel.DESTRUCTIVE,
)
def llm_letter_delete(uuid: str = "") -> dict:
    """Delete a letter."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_letter_service()
    try:
        ok = service.delete(uuid)
        if not ok:
            return {"success": False, "error": f"Letter not found: {uuid}"}
        return {"success": True, "data": {"uuid": uuid, "deleted": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to delete letter: {exc}"}
