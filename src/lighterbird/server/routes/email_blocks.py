"""Spam block REST API routes.

Blocks are identified by UUID (surrogate key).
Edit/delete operations are GUI-only via the list tab.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from lighterbird.email.service import EmailService
from lighterbird.server.deps import get_email_service

router = APIRouter(prefix="/api/v1/email/blocks", tags=["email-blocks"])


class BlockUpdateRequest(BaseModel):
    note: str = Field(default="", description="Updated note/reason for the block")

    model_config = {"extra": "forbid"}


@router.get("")
def list_blocks(email_svc: EmailService = Depends(get_email_service)):
    """List all spam blocks."""
    blocks = email_svc.spam.list_blocks()
    return {"blocks": blocks, "total": len(blocks)}


@router.patch("/{block_uuid}")
def update_block(
    block_uuid: str,
    data: BlockUpdateRequest,
    email_svc: EmailService = Depends(get_email_service),
):
    """Update a block's note."""
    updated = email_svc.spam.update_block(block_uuid, note=data.note)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Block not found: {block_uuid}")
    return updated


@router.delete("/{block_uuid}")
def delete_block(
    block_uuid: str,
    email_svc: EmailService = Depends(get_email_service),
):
    """Delete a block by UUID."""
    block = email_svc.spam.get_block(block_uuid)
    if not block:
        raise HTTPException(status_code=404, detail=f"Block not found: {block_uuid}")
    email_svc.spam.unblock(block_uuid)
    return {"status": "deleted", "uuid": block_uuid}
