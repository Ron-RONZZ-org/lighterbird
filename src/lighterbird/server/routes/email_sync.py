"""Email sync REST API routes — start sync + poll progress.

Extracted from ``email.py`` to stay under the 500-line limit.
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, Depends, HTTPException

from lighterbird.email.service import EmailService
from lighterbird.server.deps import get_email_service
from lighterbird.server.schemas import (
    AccountSyncStatus,
    SyncProgressResponse,
    SyncRequest,
    SyncStartResponse,
    SyncStatusResponse,
)
from lighterbird.email.imap.client import decode_imap_utf7
from lighterbird.server.sync_progress import get_sync_progress_tracker

router = APIRouter(prefix="/api/v1/email", tags=["email"])


@router.get("/sync/status", response_model=SyncStatusResponse)
def get_sync_status():
    """Return per-account sync state and whether startup sync is complete.

    This endpoint is polled by the frontend to determine whether to
    show the sync overlay (during initial startup) or a subtle sync
    status bar (during normal operation).
    """
    from lighterbird.email.imap.idle import get_imap_idle_manager
    from lighterbird.server.sync_state import get_sync_state_manager

    state_mgr = get_sync_state_manager()
    idle_mgr = get_imap_idle_manager()

    all_states = state_mgr.all_states()
    idle_statuses = idle_mgr.status_all()

    # Merge idle thread status into account sync states
    idle_map: dict[str, dict] = {}
    for idle_info in idle_statuses:
        acct = idle_info.get("account_email", "")
        idle_map[acct] = idle_info

    accounts = []
    for acct_state in all_states:
        acct_email = acct_state["account_email"]
        idle_info = idle_map.get(acct_email, {})
        accounts.append(AccountSyncStatus(
            account_email=acct_email,
            status=acct_state.get("status", "startup-syncing"),
            last_sync_at=acct_state.get("last_sync_at"),
            last_error=acct_state.get("last_error"),
            idle_alive=idle_info.get("alive", False),
            idle_supported=acct_state.get("idle_supported"),
            last_idle_heartbeat=acct_state.get("last_idle_heartbeat"),
            reconnects=idle_info.get("reconnects", 0),
        ))

    return SyncStatusResponse(
        startup_complete=state_mgr.startup_completed,
        accounts=accounts,
    )


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
            folders = [req.folder_name] if req.folder_name else None
            if req.account_email:
                result = email_svc.sync_account(
                    req.account_email,
                    folders=folders,
                    folders_only=req.folders_only,
                    progress_tracker=tracker,
                    task_id=task_id,
                )
            elif req.folder_name:
                # Sync a specific folder (e.g. Trash) for all accounts
                total = 0
                new = 0
                errors = []
                for acct in email_svc.list_accounts():
                    email = acct["email"]
                    sr = email_svc.sync_account(
                        email, folders=[req.folder_name],
                        folders_only=req.folders_only,
                        progress_tracker=tracker,
                        task_id=task_id,
                        manage_progress=False,
                    )
                    total += sr.total
                    new += sr.new
                    errors.extend(sr.errors)
                tracker.complete(task_id, result_total=total, result_new=new,
                                 errors=errors or None)
            elif req.folders_only:
                # Register folder hierarchy for all accounts
                total = 0
                errors = []
                for acct in email_svc.list_accounts():
                    email = acct["email"]
                    sr = email_svc.sync_account(
                        email, folders_only=True,
                        progress_tracker=tracker,
                        task_id=task_id,
                        manage_progress=False,
                    )
                    total += sr.total
                    errors.extend(sr.errors)
                tracker.complete(task_id, result_total=total, result_new=0,
                                 errors=errors or None)
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
        finally:
            # Ensure the task is always completed, even when the IMAP sync
            # function returns early (e.g. connection failure before the
            # progress_tracker.complete() call inside sync_account()).
            prog = tracker.get(task_id)
            if prog and prog["status"] == "running":
                tracker.complete(task_id, errors=["Sync failed or timed out"])

    thread = threading.Thread(target=_run_sync, daemon=True)
    thread.start()

    return SyncStartResponse(task_id=task_id, account_email=req.account_email)


@router.get("/sync/progress/{task_id}", response_model=SyncProgressResponse)
def get_sync_progress(task_id: str):
    """Poll progress of a sync task started via ``POST /api/v1/email/sync``.

    Folder names from IMAP are stored in modified UTF-7 encoding (RFC 3501
    §5.1.3).  Decode them before returning so the frontend displays proper
    Unicode (accents, emoji, etc.) in the progress bar.
    """
    tracker = get_sync_progress_tracker()
    progress = tracker.get(task_id)
    if progress is None:
        raise HTTPException(status_code=404, detail=f"Sync task not found: {task_id}")
    if progress.get("folder_name"):
        progress["folder_name"] = decode_imap_utf7(progress["folder_name"])
    return SyncProgressResponse(**progress)
