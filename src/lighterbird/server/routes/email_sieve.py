"""Sieve filter REST API routes.

Scripts are global; per-account activation is tracked separately.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from lighterbird.server.deps import get_email_service
from lighterbird.server.schemas import (
    SieveScriptCreate,
    SieveScriptUpdate,
    SieveActivateRequest,
    SieveScriptResponse,
    SieveScriptListResponse,
    SieveValidateRequest,
    SieveValidateResponse,
)
from lighterbird.email.service import EmailService
from lighterbird.email.filters.sieve import validate_sieve

router = APIRouter(prefix="/api/v1/email/sieve", tags=["email", "sieve"])


def _row_to_response(row: dict) -> SieveScriptResponse:
    """Convert a script dict to the Pydantic response model."""
    return SieveScriptResponse(
        uuid=row["uuid"] if "uuid" in row else row.get("uuid", ""),
        name=row["name"],
        content=row.get("content", ""),
        system=bool(row.get("system", 0)),
        created_at=row.get("created_at", ""),
        modified_at=row.get("modified_at", ""),
        aktivado=row.get("aktivado"),
    )


@router.get("", response_model=SieveScriptListResponse)
@router.get("/", response_model=SieveScriptListResponse)
def list_scripts(
    account_uuid: str | None = Query(default=None, alias="account_uuid"),
    email_svc: EmailService = Depends(get_email_service),
):
    """List Sieve scripts. When ``account_uuid`` is given, includes
    per-account activation status and the virtual ``_spam_blocks`` script.
    """
    scripts = email_svc.sieve.list_scripts(konto_id=account_uuid)
    return SieveScriptListResponse(
        scripts=[_row_to_response(s) for s in scripts]
    )


@router.get("/{name}", response_model=SieveScriptResponse)
def get_script(
    name: str,
    account_uuid: str | None = Query(default=None, alias="account_uuid"),
    email_svc: EmailService = Depends(get_email_service),
):
    """Get a script by name. With ``account_uuid``, includes activation info."""
    if account_uuid:
        script = email_svc.sieve.get_script_with_activation(name, konto_id=account_uuid)
    else:
        script = email_svc.sieve.get_script(name)
    if not script:
        raise HTTPException(status_code=404, detail=f"Sieve script '{name}' not found.")
    return _row_to_response(script)


@router.post("", response_model=SieveScriptResponse, status_code=201)
@router.post("/", response_model=SieveScriptResponse, status_code=201)
def create_script(
    data: SieveScriptCreate,
    email_svc: EmailService = Depends(get_email_service),
):
    """Create a new global Sieve script."""
    try:
        script = email_svc.sieve.create_script(
            nomo=data.name,
            content=data.content,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _row_to_response(script)


@router.put("/{name}", response_model=SieveScriptResponse)
def update_script(
    name: str,
    data: SieveScriptUpdate,
    email_svc: EmailService = Depends(get_email_service),
):
    """Update a global Sieve script."""
    try:
        script = email_svc.sieve.update_script(
            nomo=name,
            new_name=data.name,
            content=data.content,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not script:
        raise HTTPException(status_code=404, detail=f"Sieve script '{name}' not found.")
    return _row_to_response(script)


@router.delete("/{name}")
def delete_script(
    name: str,
    email_svc: EmailService = Depends(get_email_service),
):
    """Delete a global Sieve script (removes activations on all accounts)."""
    try:
        deleted = email_svc.sieve.delete_script(name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Sieve script '{name}' not found.")
    return {"status": "deleted", "name": name}


@router.post("/{name}/activate", response_model=SieveScriptResponse)
def activate_script(
    name: str,
    data: SieveActivateRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Activate a script on a specific account."""
    if not data.account_uuid:
        raise HTTPException(status_code=422, detail="account_uuid is required")
    script = email_svc.sieve.activate_script(name, konto_id=data.account_uuid)
    if not script:
        raise HTTPException(status_code=404, detail=f"Sieve script '{name}' not found.")
    return _row_to_response(script)


@router.post("/{name}/deactivate", response_model=SieveScriptResponse)
def deactivate_script(
    name: str,
    data: SieveActivateRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Deactivate a script on a specific account."""
    if not data.account_uuid:
        raise HTTPException(status_code=422, detail="account_uuid is required")
    script = email_svc.sieve.deactivate_script(name, konto_id=data.account_uuid)
    if not script:
        raise HTTPException(status_code=404, detail=f"Sieve script '{name}' not found.")
    return _row_to_response(script)


@router.post("/validate", response_model=SieveValidateResponse)
def validate_script_content(data: SieveValidateRequest):
    """Validate Sieve script syntax without saving."""
    is_valid, error = validate_sieve(data.content)
    return SieveValidateResponse(is_valid=is_valid, error=error)
