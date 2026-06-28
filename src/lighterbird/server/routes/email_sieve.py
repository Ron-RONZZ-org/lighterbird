"""Sieve script REST API routes.

Sieve scripts are identified by ``name`` (natural key). Accounts
are identified by ``email`` (natural key).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from lighterbird.server.deps import get_email_service
from lighterbird.server.schemas import (
    SieveScriptCreate, SieveScriptUpdate, SieveScriptResponse,
    SieveScriptListResponse,
    SieveActivateRequest, SieveActivationInfo,
    SievePriorityUpdate, SieveAnalyzeRequest, SieveAnalyzeResponse,
    SieveValidateRequest, SieveValidateResponse,
)
from lighterbird.email.service import EmailService

router = APIRouter(prefix="/api/v1/sieve", tags=["sieve"])


def _resolve_account(email_svc: EmailService, account_email: str) -> str:
    """Resolve an account email, raising 404 if not found."""
    if not account_email:
        raise HTTPException(status_code=422, detail="account_email is required")
    acct = email_svc.get_account(account_email)
    if not acct:
        raise HTTPException(
            status_code=404,
            detail=f"Account '{account_email}' not found. "
                   f"Run !sync --email first to register your accounts.",
        )
    return account_email


def _script_to_response(script: dict) -> SieveScriptResponse | dict:
    """Convert a script dict to a SieveScriptResponse."""
    if script is None:
        return {}
    akt = script.get("aktivado")
    return SieveScriptResponse(
        name=script.get("name", ""),
        content=script.get("content", ""),
        system=script.get("system", False),
        created_at=script.get("created_at", ""),
        modified_at=script.get("modified_at", ""),
        aktivado=SieveActivationInfo(
            active=akt["active"],
            priority=akt.get("priority", 0),
            man_sync=akt.get("man_sync", False),
            created_at=akt.get("created_at", ""),
            modified_at=akt.get("modified_at", ""),
        ) if akt else None,
    )


@router.get("/scripts", response_model=SieveScriptListResponse)
def list_scripts(
    account_email: str | None = Query(default=None, alias="account_email"),
    email_svc: EmailService = Depends(get_email_service),
):
    """List Sieve scripts. When ``account_email`` is given, includes
    per-account activation info."""
    scripts = email_svc.sieve.list_scripts(konto_id=account_email)
    return SieveScriptListResponse(
        scripts=[_script_to_response(s) for s in scripts]
    )


@router.post("/scripts", response_model=SieveScriptResponse, status_code=201)
def create_script(
    data: SieveScriptCreate,
    email_svc: EmailService = Depends(get_email_service),
):
    try:
        script = email_svc.sieve.create_script(nomo=data.name, content=data.content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _script_to_response(script)


@router.get("/scripts/{name}", response_model=SieveScriptResponse)
def get_script(
    name: str,
    account_email: str | None = Query(default=None, alias="account_email"),
    email_svc: EmailService = Depends(get_email_service),
):
    """Get a script by name. With ``account_email``, includes activation info."""
    if account_email:
        script = email_svc.sieve.get_script_with_activation(name, konto_id=account_email)
    else:
        script = email_svc.sieve.get_script(name)
    if not script:
        raise HTTPException(status_code=404, detail=f"Script not found: {name}")
    return _script_to_response(script)


@router.patch("/scripts/{name}", response_model=SieveScriptResponse)
def update_script(
    name: str,
    data: SieveScriptUpdate,
    email_svc: EmailService = Depends(get_email_service),
):
    try:
        script = email_svc.sieve.update_script(name, new_name=data.name, content=data.content)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not script:
        raise HTTPException(status_code=404, detail=f"Script not found: {name}")
    return _script_to_response(script)


@router.delete("/scripts/{name}")
def delete_script(name: str, email_svc: EmailService = Depends(get_email_service)):
    deleted = email_svc.sieve.delete_script(name)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Script not found: {name}")
    return {"status": "deleted"}


@router.post("/scripts/{name}/activate", response_model=SieveScriptResponse)
def activate_script(
    name: str,
    data: SieveActivateRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    konto_id = _resolve_account(email_svc, data.account_email)
    script = email_svc.sieve.activate_script(
        name, konto_id=konto_id, priority=data.priority,
    )
    if not script:
        raise HTTPException(status_code=404, detail=f"Script not found: {name}")
    return _script_to_response(script)


@router.post("/scripts/{name}/deactivate", response_model=SieveScriptResponse)
def deactivate_script(
    name: str,
    data: SieveActivateRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    konto_id = _resolve_account(email_svc, data.account_email)
    script = email_svc.sieve.deactivate_script(name, konto_id=konto_id)
    if not script:
        raise HTTPException(status_code=404, detail=f"Script not found: {name}")
    return _script_to_response(script)


@router.post("/scripts/{name}/priority", response_model=SieveScriptResponse)
def set_priority(
    name: str,
    data: SievePriorityUpdate,
    email_svc: EmailService = Depends(get_email_service),
):
    konto_id = _resolve_account(email_svc, data.account_email)
    script = email_svc.sieve.set_priority(name, konto_id=konto_id, priority=data.priority)
    if not script:
        raise HTTPException(status_code=404, detail=f"Script not found: {name}")
    return _script_to_response(script)


@router.post("/analyze", response_model=SieveAnalyzeResponse)
def analyze_scripts(
    data: SieveAnalyzeRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Analyze and combine multiple Sieve scripts with conflict detection."""
    from lighterbird.email.filters.combiner import combine_scripts

    scripts = [{"name": s.name, "content": s.content} for s in data.scripts]
    combined, warnings = combine_scripts(scripts)

    return SieveAnalyzeResponse(
        combined=combined,
        warnings=[w.model_dump() if hasattr(w, 'model_dump') else w for w in warnings],
        is_valid=True,
    )


@router.post("/validate", response_model=SieveValidateResponse)
def validate_sieve_script(
    data: SieveValidateRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    from lighterbird.email.filters.sieve import validate_sieve

    is_valid, error = validate_sieve(data.content)
    return SieveValidateResponse(is_valid=is_valid, error=error or "")
