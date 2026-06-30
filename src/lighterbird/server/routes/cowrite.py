"""Co-writing API route.

``POST /api/v1/cowrite`` — Send form content to LLM for editing.

Returns structured diffs (computed via ``difflib`` on the full revised
text returned by the LLM), along with the raw revised text for each
field.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from lighterbird.server.cowrite.engine import cowrite as cowrite_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["cowrite"])


@router.post("/cowrite")
async def cowrite_endpoint(data: dict) -> dict:
    """Accept form content + instruction, return structured diffs.

    Request body:
        ``form_type`` (str): Type of form (``"email-send"``,
            ``"todo-add"``, ``"journal-write"``).
        ``fields`` (dict): Current form content ``{field: text}``.
        ``instruction`` (str): User's editing instruction.
        ``context_mode`` (str, optional): ``"auto"`` or ``"none"``.
            Default ``"auto"``.

    Response:
        ``edits`` (dict): ``{field: [EditOp, ...]}``.
        ``revised`` (dict): ``{field: full_revised_text}``.
        ``original`` (dict): ``{field: original_text}``.
        ``session_id`` (str): Unique session identifier.
    """
    form_type = data.get("form_type", "").strip()
    fields = data.get("fields", {})
    instruction = data.get("instruction", "").strip()
    context_mode = data.get("context_mode", "auto")

    if not form_type:
        raise HTTPException(status_code=400, detail="form_type is required.")
    if not fields:
        raise HTTPException(status_code=400, detail="fields is required.")
    if not instruction:
        raise HTTPException(
            status_code=400,
            detail="instruction is required — tell the LLM what to do.",
        )

    # Validate that all field values are strings
    for key, val in fields.items():
        if not isinstance(val, str):
            raise HTTPException(
                status_code=400,
                detail=f"Field '{key}' must be a string.",
            )

    try:
        result = await cowrite_engine(
            form_type=form_type,
            fields=fields,
            instruction=instruction,
            context_mode=context_mode,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return result
