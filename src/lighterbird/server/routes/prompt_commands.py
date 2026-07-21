"""API routes for file-based prompt commands (/* prefix).

Endpoints:
- GET  /api/v1/prompt-commands/list       — autocomplete source
- POST /api/v1/prompt-commands/expand     — preview expanded template
- POST /api/v1/prompt-commands/execute    — expand + multi-round tool loop
- POST /api/v1/prompt-commands/execute/resume  — resume paused HITL session
- POST /api/v1/prompt-commands/execute/stream  — SSE streaming (no tools)

The execute endpoint uses lightercore's unified ``execute_prompt_command()``
for the full pipeline: load → expand → message build → domain filter →
tool loop → response formatting.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from lightercore.paths import config_dir
from lighterllm.prompt_commands import (
    execute_prompt_command,
    expand_prompt_template,
    list_prompt_commands,
    load_prompt_command,
    prompt_command_event_stream,
)

from lighterbird.core.system_prompt import load_system_prompt
from lighterbird.server.command.registry import (
    dispatch,
    get_command_level,
    get_definitions,
    get_handler_metadata,
)
from lighterbird.server.llm.provider import get_provider
from lighterbird.server.llm.render import render_markdown
from lighterbird.server.llm.tool_loop import resume_execution

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prompt-commands", tags=["prompt-commands"])


def _commands_dir() -> str:
    """Return the commands directory path (config_dir / 'commands')."""
    return str(config_dir() / "commands")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _dispatch_path(path: str, flags: dict) -> dict:
    """Dispatch a command by dot-separated path."""
    return dispatch(path.split("."), flags)


# ── GET /list ────────────────────────────────────────────────────────────────


@router.get("/list")
async def list_commands_endpoint() -> list[dict[str, Any]]:
    """Return all available prompt commands (name + description).
    Used by the frontend for autocomplete.
    """
    from pathlib import Path

    cmds = list_prompt_commands(Path(_commands_dir()))
    return [
        {"name": c.name, "description": c.description, "param_count": c.param_count}
        for c in cmds
    ]


# ── POST /expand ─────────────────────────────────────────────────────────────


@router.post("/expand")
async def expand_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Expand a prompt command template with positional args.
    Returns 404 if the command file does not exist.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    from pathlib import Path

    cmd = load_prompt_command(Path(_commands_dir()), name)
    if cmd is None:
        available = [c.name for c in list_prompt_commands(Path(_commands_dir()))]
        raise HTTPException(
            status_code=404,
            detail=(
                f"Prompt command '{name}' not found. "
                f"Available: {', '.join(available) or '(none)'}"
            ),
        )

    expanded = expand_prompt_template(cmd.template, args)

    return {
        "name": cmd.name,
        "description": cmd.description,
        "template": cmd.template,
        "expanded": expanded,
        "param_count": cmd.param_count,
    }


# ── POST /execute ────────────────────────────────────────────────────────────


@router.post("/execute")
async def execute_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Expand a prompt command and execute with multi-round tool-calling.

    Delegates to :func:`~lighterllm.prompt_commands.execute_prompt_command`
    for the full pipeline: load → expand → message build → domain filter →
    tool loop → response formatting.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    from pathlib import Path

    result = await execute_prompt_command(
        name=name,
        args=args,
        commands_dir=Path(_commands_dir()),
        provider=get_provider(),
        system_prompt_loader=load_system_prompt,
        definitions_loader=get_definitions,
        dispatch_fn=_dispatch_path,
        get_handler_metadata_fn=get_handler_metadata,
        get_command_level_fn=get_command_level,
        title_prefix="/*",
    )

    if result.get("status_code"):
        raise HTTPException(
            status_code=result["status_code"],
            detail=result.get("detail", ""),
        )
    return result


# ── POST /execute/resume (HITL) ──────────────────────────────────────────────


@router.post("/execute/resume")
async def execute_resume_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Resume a paused prompt command execution after user confirmation.

    Request body:
        session_id (str): The session UUID from ``confirm_tool`` response.
        confirmed (bool, optional): Apply this decision to ALL tools.
        decisions (dict[int, bool], optional): Per-tool-index approval.

    Returns:
        Same response types as ``/execute``.
    """
    session_id = data.get("session_id", "")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required.")

    provider = get_provider()
    if not provider.is_available():
        return {
            "type": "status",
            "title": "Prompt Command",
            "data": {"message": "LLM not configured."},
        }

    try:
        result = await resume_execution(
            session_id=session_id,
            decisions=data.get("decisions"),
            confirmed=data.get("confirmed"),
            provider=provider,
            dispatch_fn=_dispatch_path,
            get_handler_metadata_fn=get_handler_metadata,
            get_command_level_fn=get_command_level,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Handle nested confirm_tool (LLM wants more approvals)
    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    reply = result if isinstance(result, str) and result.strip() else None
    if reply:
        return {
            "type": "chat",
            "title": "Prompt Command",
            "data": {"html": render_markdown(reply), "actions": []},
        }

    return {
        "type": "chat",
        "title": "Prompt Command",
        "data": {"html": "<p><em>(command completed)</em></p>", "actions": []},
    }


# ── POST /execute/stream (SSE) ───────────────────────────────────────────────


@router.post("/execute/stream")
async def execute_stream_endpoint(data: dict[str, Any]) -> StreamingResponse:
    """Streaming variant of ``/execute`` — SSE without tool-calling.

    Delegates to :func:`~lighterllm.prompt_commands.prompt_command_event_stream`
    for the shared SSE generation.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    from pathlib import Path

    return StreamingResponse(
        prompt_command_event_stream(
            name=name,
            args=args,
            commands_dir=Path(_commands_dir()),
            provider=get_provider(),
            system_prompt_loader=load_system_prompt,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
