"""Contacts REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from lighterbird.server.deps import get_contact_service
from lighterbird.contacts.services import ContactService

router = APIRouter(prefix="/api/v1/contacts", tags=["contacts"])


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
    contact_data = {
        "nomo": data.get("name", ""),
        "retposto": data.get("email", ""),
        "telefonnumero": data.get("phone", ""),
        "organizo": data.get("organization", ""),
        "notoj": data.get("notes", ""),
    }
    contact = svc.create(contact_data)
    return contact


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
    updates = {}
    field_map = {
        "name": "nomo",
        "email": "retposto",
        "phone": "telefonnumero",
        "organization": "organizo",
        "notes": "notoj",
    }
    for json_key, db_key in field_map.items():
        if json_key in data:
            updates[db_key] = data[json_key]
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = svc.update(uuid, updates)
    return result


@router.delete("/contacts/{uuid}", status_code=204)
def delete_contact(uuid: str, svc: ContactService = Depends(get_contact_service)):
    svc.delete(uuid)
