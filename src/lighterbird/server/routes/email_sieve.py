"""Sieve filter REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from lighterbird.server.deps import get_email_service
from lighterbird.server.schemas import (
    SieveScriptCreate,
    SieveScriptUpdate,
    SieveScriptResponse,
    SieveScriptListResponse,
    SieveValidateRequest,
    SieveValidateResponse,
)
from lighterbird.email.service import EmailService
from lighterbird.email.filters.sieve import validate_sieve

router = APIRouter(prefix="/api/v1/email/sieve", tags=["email", "sieve"])


def _row_to_response(row: dict) -> SieveScriptResponse:
    return SieveScriptResponse(
        uuid=row["uuid"],
        account_uuid=row["konto_id"],
        name=row["nomo"],
        content=row.get("content", ""),
        active=bool(row.get("active", 0)),
        system=bool(row.get("system", 0)),
        man_sync=bool(row.get("man_sync", 1)),
        created_at=row.get("kreita_je", ""),
        modified_at=row.get("modifita_je", ""),
    )


def _resolve_account(email_svc: EmailService, account_uuid: str = "") -> str:
    """Resolve an account UUID, defaulting to the first account with ManageSieve."""
    if account_uuid:
        return account_uuid
    accounts = email_svc.list_accounts()
    if not accounts:
        raise HTTPException(status_code=404, detail="No email accounts configured.")
    # Prefer account with ManageSieve
    for acct in accounts:
        if acct.get("managesieve_host", ""):
            return acct["uuid"]
    return accounts[0]["uuid"]


@router.get("", response_model=SieveScriptListResponse)
@router.get("/", response_model=SieveScriptListResponse)
def list_scripts(
    account_uuid: str | None = Query(default=None, alias="account_uuid"),
    email_svc: EmailService = Depends(get_email_service),
):
    """List Sieve scripts, optionally filtered by account."""
    if account_uuid:
        scripts = email_svc.sieve.list_scripts(konto_id=account_uuid)
    else:
        scripts = email_svc.sieve.list_scripts()
    return SieveScriptListResponse(
        scripts=[_row_to_response(s) for s in scripts]
    )


@router.get("/{name}", response_model=SieveScriptResponse)
def get_script(
    name: str,
    account_uuid: str | None = Query(default=None, alias="account_uuid"),
    email_svc: EmailService = Depends(get_email_service),
):
    """Get a single Sieve script by name."""
    konto_id = _resolve_account(email_svc, account_uuid or "")
    script = email_svc.sieve.get_script(name, konto_id=konto_id)
    if not script:
        raise HTTPException(status_code=404, detail=f"Sieve script '{name}' not found.")
    return _row_to_response(script)


@router.post("", response_model=SieveScriptResponse, status_code=201)
@router.post("/", response_model=SieveScriptResponse, status_code=201)
def create_script(
    data: SieveScriptCreate,
    email_svc: EmailService = Depends(get_email_service),
):
    """Create a new Sieve script."""
    konto_id = _resolve_account(email_svc, data.account_uuid)
    try:
        script = email_svc.sieve.create_script(
            konto_id=konto_id,
            nomo=data.name,
            content=data.content,
            active=data.active,
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
    """Update a Sieve script."""
    konto_id = _resolve_account(email_svc, data.account_uuid or "")
    try:
        script = email_svc.sieve.update_script(
            nomo=name,
            konto_id=konto_id,
            new_name=data.name,
            content=data.content,
            active=data.active,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not script:
        raise HTTPException(status_code=404, detail=f"Sieve script '{name}' not found.")
    return _row_to_response(script)


@router.delete("/{name}")
def delete_script(
    name: str,
    account_uuid: str | None = Query(default=None, alias="account_uuid"),
    email_svc: EmailService = Depends(get_email_service),
):
    """Delete a Sieve script."""
    konto_id = _resolve_account(email_svc, account_uuid or "")
    try:
        deleted = email_svc.sieve.delete_script(name, konto_id=konto_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Sieve script '{name}' not found.")
    return {"status": "deleted", "name": name}


@router.post("/{name}/activate", response_model=SieveScriptResponse)
def activate_script(
    name: str,
    account_uuid: str | None = Query(default=None, alias="account_uuid"),
    email_svc: EmailService = Depends(get_email_service),
):
    """Activate a Sieve script."""
    konto_id = _resolve_account(email_svc, account_uuid or "")
    script = email_svc.sieve.activate_script(name, konto_id=konto_id)
    if not script:
        raise HTTPException(status_code=404, detail=f"Sieve script '{name}' not found.")
    return _row_to_response(script)


@router.post("/validate", response_model=SieveValidateResponse)
def validate_script_content(data: SieveValidateRequest):
    """Validate Sieve script syntax without saving."""
    is_valid, error = validate_sieve(data.content)
    return SieveValidateResponse(is_valid=is_valid, error=error)
