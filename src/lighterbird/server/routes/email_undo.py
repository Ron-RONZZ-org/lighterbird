"""Undo API routes for email operations.

Provides a single endpoint:

- ``POST /api/v1/email/actions/undo/{operation_id}`` — Revert a scheduled
  operation (trash, hard-delete, spam, fraud) before its commit timer fires.

Requires the ``delay_seconds`` parameter on the original action endpoint
(see :mod:`lighterbird.server.routes.email_actions` and
:mod:`lighterbird.server.routes.email_spam`).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from lighterbird.email.undo import get_undo_registry

router = APIRouter(prefix="/api/v1/email/actions", tags=["email-actions"])


@router.post("/undo/{operation_id}")
def undo_operation(operation_id: str):
    """Revert a pending email operation (trash, hard-delete, spam, fraud).

    The operation must have been scheduled with ``delay_seconds`` > 0 and
    the timer must not have expired yet.

    Returns:
        Dict with ``status``, ``operation_id``, and ``action``.
    """
    registry = get_undo_registry()
    try:
        registry.undo(operation_id)
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    return {
        "status": "reverted",
        "operation_id": operation_id,
    }
