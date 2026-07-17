"""LLM tools for the contacts domain.

Tools:
    - ``contacts.find`` -- Search contacts by name, email, or organization
    - ``contacts.read`` -- Full contact details by UUID
    - ``contacts.create`` -- Add a new contact
    - ``contacts.update`` -- Modify an existing contact
    - ``contacts.delete`` -- Delete a contact
"""

from __future__ import annotations

from typing import Any

from lightercore.permissions import PermissionLevel

from lighterbird.server.deps import get_contact_service
from lighterbird.server.llm.tools import llm_tool


# ── Find contacts ─────────────────────────────────────────────────────────────


@llm_tool(
    name="contacts.find",
    description=(
        "Search contacts by name, email, or organization. "
        "Returns matching contacts with basic info (name, email, phone)."
    ),
    params=[
        {"name": "query", "type": "string", "description": "Search term for name, email, or organization"},
        {"name": "email", "type": "string", "description": "Exact email search"},
        {"name": "organization", "type": "string", "description": "Organization name filter"},
        {"name": "max_results", "type": "number", "description": "Maximum results (default 20)"},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_contacts_find(**kwargs: Any) -> dict:
    """Search contacts."""
    query = kwargs.get("query", "") or ""
    email = kwargs.get("email", "") or ""
    org = kwargs.get("organization", "") or ""
    limit = int(kwargs.get("max_results", 20))

    service = get_contact_service()
    try:
        if email:
            contact = service.find_by_email(email)
            if contact:
                return {"success": True, "data": [_contact_preview(contact)], "total": 1}
            return {"success": True, "data": [], "total": 0}

        if query or org:
            results = service.search(query=query, organization=org, limit=limit)
            return {"success": True, "data": [_contact_preview(r) for r in results], "total": len(results)}

        # List all contacts (no filter)
        from lightercore.crud import CRUDService
        results = service.list(limit=limit)
        return {"success": True, "data": [_contact_preview(r) for r in results], "total": len(results)}
    except Exception as exc:
        return {"success": False, "error": f"Contact search failed: {exc}"}


def _contact_preview(c: dict) -> dict:
    """Return a safe preview of a contact dict."""
    return {
        "uuid": c.get("uuid", ""),
        "display_name": c.get("display_name", ""),
        "given_name": c.get("given_name", ""),
        "family_name": c.get("family_name", ""),
        "email": c.get("email", ""),
        "phone": c.get("phone", ""),
        "organization": c.get("organization", ""),
        "role": c.get("role", ""),
    }


# ── Read contact ──────────────────────────────────────────────────────────────


@llm_tool(
    name="contacts.read",
    description="Get full contact details by UUID, including all emails, phones, and addresses.",
    params=[
        {"name": "uuid", "type": "string", "description": "Contact UUID", "required": True},
    ],
    permission_level=PermissionLevel.READ,
)
def llm_contacts_read(uuid: str = "") -> dict:
    """Get full contact details."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_contact_service()
    try:
        contact = service.get(uuid)
        if not contact:
            return {"success": False, "error": f"Contact not found: {uuid}"}
        return {"success": True, "data": dict(contact)}
    except Exception as exc:
        return {"success": False, "error": f"Failed to read contact: {exc}"}


# ── Create contact ────────────────────────────────────────────────────────────


@llm_tool(
    name="contacts.create",
    description="Add a new contact with name, email, phone, and organization info.",
    params=[
        {"name": "given_name", "type": "string", "description": "Given (first) name", "required": True},
        {"name": "family_name", "type": "string", "description": "Family (last) name"},
        {"name": "email", "type": "string", "description": "Primary email address"},
        {"name": "phone", "type": "string", "description": "Primary phone number"},
        {"name": "organization", "type": "string", "description": "Organization or company"},
        {"name": "role", "type": "string", "description": "Job title or role"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_contacts_create(**kwargs: Any) -> dict:
    """Create a new contact."""
    given_name = kwargs.get("given_name", "")
    if not given_name:
        return {"success": False, "error": "given_name is required"}

    data: dict[str, Any] = {
        "given_name": given_name,
        "family_name": kwargs.get("family_name", ""),
        "email": kwargs.get("email", ""),
        "phone": kwargs.get("phone", ""),
        "organization": kwargs.get("organization", ""),
        "role": kwargs.get("role", ""),
    }

    service = get_contact_service()
    try:
        result = service.create(data)
        return {"success": True, "data": {"uuid": result.get("uuid", ""), "display_name": result.get("display_name", "")}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to create contact: {exc}"}


# ── Update contact ────────────────────────────────────────────────────────────


@llm_tool(
    name="contacts.update",
    description="Modify an existing contact. Only provided fields are updated.",
    params=[
        {"name": "uuid", "type": "string", "description": "Contact UUID to modify", "required": True},
        {"name": "given_name", "type": "string", "description": "New given name"},
        {"name": "family_name", "type": "string", "description": "New family name"},
        {"name": "email", "type": "string", "description": "New primary email"},
        {"name": "phone", "type": "string", "description": "New primary phone"},
        {"name": "organization", "type": "string", "description": "New organization"},
        {"name": "role", "type": "string", "description": "New job title"},
    ],
    permission_level=PermissionLevel.WRITE,
)
def llm_contacts_update(**kwargs: Any) -> dict:
    """Modify a contact."""
    uuid = kwargs.get("uuid", "")
    if not uuid:
        return {"success": False, "error": "uuid is required"}

    data: dict[str, Any] = {}
    for field in ("given_name", "family_name", "email", "phone", "organization", "role"):
        if kwargs.get(field) is not None:
            data[field] = kwargs[field]

    if not data:
        return {"success": False, "error": "No fields to update"}

    service = get_contact_service()
    try:
        result = service.update(uuid, data)
        if not result:
            return {"success": False, "error": f"Contact not found: {uuid}"}
        return {"success": True, "data": {"uuid": uuid, "updated": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to update contact: {exc}"}


# ── Delete contact ────────────────────────────────────────────────────────────


@llm_tool(
    name="contacts.delete",
    description="Permanently delete a contact by UUID.",
    params=[
        {"name": "uuid", "type": "string", "description": "Contact UUID to delete", "required": True},
    ],
    permission_level=PermissionLevel.DESTRUCTIVE,
)
def llm_contacts_delete(uuid: str = "") -> dict:
    """Delete a contact."""
    if not uuid:
        return {"success": False, "error": "uuid is required"}
    service = get_contact_service()
    try:
        ok = service.delete(uuid)
        if not ok:
            return {"success": False, "error": f"Contact not found: {uuid}"}
        return {"success": True, "data": {"uuid": uuid, "deleted": True}}
    except Exception as exc:
        return {"success": False, "error": f"Failed to delete contact: {exc}"}
