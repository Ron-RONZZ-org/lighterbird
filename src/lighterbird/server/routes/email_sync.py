"""Email sync REST API routes — start sync + poll progress.

Extracted from ``email.py`` to stay under the 500-line limit.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException

from lighterbird.email.service import EmailService
from lighterbird.server.deps import get_email_service
from lighterbird.server.schemas import (
    SyncProgressResponse,
    SyncRequest,
    SyncStartResponse,
)
from lighterbird.server.sync_progress import get_sync_progress_tracker

router = APIRouter(prefix="/api/v1/email", tags=["email"])


@router.post("/sync/start", response_model=SyncStartResponse)
def sync_email_start(
    req: SyncRequest = SyncRequest(),
    email_svc: EmailService = Depends(get_email_service),
):
    """Start an email sync in a background thread and return a task_id immediately.

    Progress can be polled via ``GET /api/v1/email/sync/progress/{task_id}``.
    The existing synchronous ``POST /api/v1/email/sync`` is still available
    for CLI and backward compatibility.
    """
    tracker = get_sync_progress_tracker()
    account_email = req.account_email or "all"
    task_id = tracker.start(account_email)

    def _run_sync() -> None:
        """Run the sync in a background thread."""
        try:
            if req.account_email:
                # sync_account reports its own progress via the tracker
                # (including complete() on success)
                email_svc.sync_account(
                    req.account_email,
                    progress_tracker=tracker,
                    task_id=task_id,
                )
            else:
                results = email_svc.sync_all(
                    progress_tracker=tracker,
                    task_id=task_id,
                )
                total = sum(r.get("total", 0) for r in results.values())
                new = sum(r.get("new", 0) for r in results.values())
                errors = []
                for r in results.values():
                    errors.extend(r.get("errors", []))
                tracker.complete(task_id, result_total=total, result_new=new,
                                 errors=errors or None)
        except Exception as exc:
            tracker.fail(task_id, str(exc))

    thread = threading.Thread(target=_run_sync, daemon=True)
    thread.start()

    return SyncStartResponse(task_id=task_id, account_email=req.account_email)


@router.get("/sync/progress/{task_id}", response_model=SyncProgressResponse)
def get_sync_progress(task_id: str):
    """Poll progress of a sync task started via ``POST /api/v1/email/sync``."""
    tracker = get_sync_progress_tracker()
    progress = tracker.get(task_id)
    if progress is None:
        raise HTTPException(status_code=404, detail=f"Sync task not found: {task_id}")
    return SyncProgressResponse(**progress)
