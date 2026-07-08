"""Contacts REST API routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from lighterbird.contacts.services import ContactService
from lighterbird.core.paths import safe_resolve_path
from lighterbird.server.deps import get_contact_service

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


def _parse_multi_flag(raw: str) -> list[dict[str, str]]:
    items = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            tag, val = part.split(":", 1)
            items.append({"tag": tag.strip(), "value": val.strip()})
        else:
            items.append({"tag": "", "value": part})
    return items


@router.get("/contacts")
def list_contacts(
    query: str | None = None,
    limit: int = 50,
    svc: ContactService = Depends(get_contact_service),
):
    contacts = svc.search(query or "", limit=limit) if query else svc.list(limit=limit)
    return {"contacts": contacts, "total": len(contacts)}


@router.post("/contacts", status_code=201)
def create_contact(
    data: dict,
    svc: ContactService = Depends(get_contact_service),
):
    name = data.get("name", "")
    contact_data: dict[str, Any] = {
        "given_name": name,
        "full_name": name,
        "emails": json.dumps(_parse_multi_flag(data.get("email", ""))),
        "phones": json.dumps(_parse_multi_flag(data.get("phone", ""))),
        "organization": data.get("organization", ""),
        "notes": data.get("notes", ""),
    }
    for key in ("middle_names", "date_of_birth", "place_of_birth", "address", "post_code", "position"):
        if key in data:
            contact_data[key] = data[key]
    contact = svc.create(contact_data)
    return contact


@router.post("/contacts/import-vcf", status_code=200)
def import_vcf(
    data: dict,
    svc: ContactService = Depends(get_contact_service),
):
    """Import contacts from a VCF file path."""
    path = data.get("path", "")
    if not path:
        raise HTTPException(status_code=400, detail="Path is required.")
    try:
        safe_resolve_path(path)
    except (ValueError, FileNotFoundError, IsADirectoryError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        count = svc.import_vcf(path)
        return {"imported": count, "message": f"Imported {count} contact(s)"}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ImportError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/contacts/export-vcf")
def export_vcf(
    uuid: str | None = None,
    svc: ContactService = Depends(get_contact_service),
):
    """Export contact(s) to VCF format."""
    try:
        vcf_text = svc.export_vcf(uuid=uuid)
        return {"vcf": vcf_text}
    except ImportError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/contacts/autocomplete/organization")
def autocomplete_organization(
    svc: ContactService = Depends(get_contact_service),
):
    """Return all distinct organization values for autocomplete."""
    orgs = svc.list_organizations()
    return {"values": orgs}


@router.get("/contacts/{uuid}")
def get_contact(uuid: str, svc: ContactService = Depends(get_contact_service)):
    contact = svc.get(uuid)
    if not contact:
        raise HTTPException(status_code=404, detail=f"Contact not found: {uuid[:8]}")
    return contact


@router.patch("/contacts/{uuid}")
def update_contact(
    uuid: str,
    data: dict,
    svc: ContactService = Depends(get_contact_service),
):
    updates: dict[str, Any] = {}
    field_map: dict[str, str] = {
        "name": "given_name",
        "organization": "organization",
        "notes": "notes",
        "middle_names": "middle_names",
        "date_of_birth": "date_of_birth",
        "place_of_birth": "place_of_birth",
        "address": "address",
        "post_code": "post_code",
        "position": "position",
    }
    for json_key, db_key in field_map.items():
        if json_key in data:
            updates[db_key] = data[json_key]

    if "email" in data:
        updates["emails"] = json.dumps(_parse_multi_flag(data["email"]))
    if "phone" in data:
        updates["phones"] = json.dumps(_parse_multi_flag(data["phone"]))

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = svc.update(uuid, updates)
    return result


@router.delete("/contacts/{uuid}", status_code=204)
def delete_contact(uuid: str, svc: ContactService = Depends(get_contact_service)):
    svc.delete(uuid)
