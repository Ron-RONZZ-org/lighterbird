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
    SievePriorityUpdate,
    SieveScriptResponse,
    SieveScriptListResponse,
    SieveAnalyzeRequest,
    SieveAnalyzeResponse,
    SieveValidateRequest,
    SieveValidateResponse,
)
from lighterbird.email.service import EmailService
from lighterbird.email.filters.sieve import validate_sieve
from lighterbird.email.filters.combiner import combine_scripts

router = APIRouter(prefix="/api/v1/email/sieve", tags=["email", "sieve"])


def _resolve_account(email_svc: EmailService, account_uuid: str) -> str:
    """Validate that an account UUID exists and return it.
    
    Raises HTTPException(404) if not found, providing a clear error
    instead of a raw FOREIGN KEY constraint failure.
    """
    if not account_uuid:
        raise HTTPException(status_code=422, detail="account_uuid is required")
    acct = email_svc.get_account(account_uuid)
    if not acct:
        raise HTTPException(
            status_code=404,
            detail=f"Account '{account_uuid[:8]}' not found. "
                   f"Use !email account list to see available accounts.",
        )
    return account_uuid


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
    konto_id = _resolve_account(email_svc, data.account_uuid)
    script = email_svc.sieve.activate_script(
        name, konto_id=konto_id, priority=data.priority,
    )
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
    konto_id = _resolve_account(email_svc, data.account_uuid)
    script = email_svc.sieve.deactivate_script(name, konto_id=konto_id)
    if not script:
        raise HTTPException(status_code=404, detail=f"Sieve script '{name}' not found.")
    return _row_to_response(script)


@router.post("/{name}/priority", response_model=SieveScriptResponse)
def set_script_priority(
    name: str,
    data: SievePriorityUpdate,
    email_svc: EmailService = Depends(get_email_service),
):
    """Set execution priority for a script on an account."""
    konto_id = _resolve_account(email_svc, data.account_uuid)
    script = email_svc.sieve.set_priority(name, konto_id=konto_id, priority=data.priority)
    if not script:
        raise HTTPException(status_code=404, detail=f"Sieve script '{name}' not found.")
    return _row_to_response(script)


@router.post("/{name}/activate-all")
def activate_on_all(
    name: str,
    email_svc: EmailService = Depends(get_email_service),
):
    """Activate a script on all accounts with ManageSieve configured."""
    result = email_svc.sieve.activate_all(name)
    return {"status": "ok", **result}


@router.post("/{name}/deactivate-all")
def deactivate_on_all(
    name: str,
    email_svc: EmailService = Depends(get_email_service),
):
    """Deactivate a script on all accounts where it is active."""
    result = email_svc.sieve.deactivate_all(name)
    return {"status": "ok", **result}


@router.post("/analyze", response_model=SieveAnalyzeResponse)
def analyze_scripts(data: SieveAnalyzeRequest):
    """Analyze scripts for conflicts and return combined version.

    Unlike ``/validate`` which checks a single script, this endpoint
    accepts multiple scripts and returns the combined result with
    conflict warnings.
    """
    scripts_list = [{"name": s.name, "content": s.content} for s in data.scripts]
    combined, warnings = combine_scripts(scripts_list)
    is_valid, error = validate_sieve(combined)
    return SieveAnalyzeResponse(
        combined=combined,
        warnings=[{"type": w["type"], "message": w["message"], "scripts": w["scripts"]}
                  for w in warnings],
        is_valid=is_valid,
        error=error,
    )


@router.post("/validate", response_model=SieveValidateResponse)
def validate_script_content(data: SieveValidateRequest):
    """Validate Sieve script syntax without saving."""
    is_valid, error = validate_sieve(data.content)
    return SieveValidateResponse(is_valid=is_valid, error=error)
