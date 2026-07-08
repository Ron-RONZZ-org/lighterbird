"""API routes for file-based prompt commands (/* prefix).

Endpoints:
- GET  /api/v1/prompt-commands/list       — autocomplete source
- POST /api/v1/prompt-commands/expand     — preview expanded template
- POST /api/v1/prompt-commands/execute    — expand + multi-round tool loop
- POST /api/v1/prompt-commands/execute/resume  — resume paused HITL session
- POST /api/v1/prompt-commands/execute/stream  — (deprecated) SSE without tools

The execute endpoint uses the same multi-round tool loop as the chat endpoint,
so the LLM can call tools, iterate, and produce data-backed answers.
WRITE-level tools gate behind user confirmation via the resume endpoint.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from lightercore.llm.base import defs_to_tools
from lightercore.paths import config_dir
from lightercore.prompt_commands import (
    expand_prompt_template,
    list_prompt_commands,
    load_prompt_command,
)

from lighterbird.core.ai import get_provider as _create_core_provider
from lighterbird.core.system_prompt import load_system_prompt
from lighterbird.server.command.registry import (
    dispatch,
    get_command_level,
    get_definitions,
    get_handler_metadata,
)
from lighterbird.server.llm.provider import get_provider
from lighterbird.server.llm.render import render_markdown
from lighterbird.server.llm.tool_loop import (
    resume_execution,
    run_tool_loop,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/prompt-commands", tags=["prompt-commands"])


def _commands_dir() -> str:
    """Return the commands directory path (config_dir / 'commands')."""
    return str(config_dir() / "commands")


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


# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_tool_domains(template: str) -> set[str] | None:
    """Parse tool domain declaration from a prompt command template.

    Looks for lines matching ``# +tools: domain1, domain2`` in the
    template body.  The domains are the first segment of command paths
    (e.g. ``email``, ``todo``, ``contact``).

    Returns:
        A set of domain strings, or ``None`` if no declaration is found
        (meaning include all tools).
    """
    for line in template.split("\n"):
        stripped = line.strip()
        match = re.match(r"^#\s*\+tools:\s*(.+)$", stripped, re.IGNORECASE)
        if match:
            domains = {d.strip().lower() for d in match.group(1).split(",") if d.strip()}
            return domains if domains else None
    return None


def _filter_defs_by_domain(
    defs: list[dict],
    allowed_domains: set[str] | None,
) -> list[dict]:
    """Filter command definitions to only include specified domains.

    Excludes bare group nodes (no params, no flags, empty description)
    which are pure tree scaffolding.
    """
    if allowed_domains is None:
        return defs
    return [
        d for d in defs
        if d["path"][0] in allowed_domains
        and not (
            not d.get("params") and not d.get("flags")
            and not d.get("description", "").strip()
        )
    ]


def _dispatch_path(path: str, flags: dict) -> dict:
    """Dispatch a command by dot-separated path."""
    return dispatch(path.split("."), flags)


# ── POST /execute ────────────────────────────────────────────────────────────


@router.post("/execute")
async def execute_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Expand a prompt command and execute with multi-round tool-calling.

    The LLM receives the expanded template plus tool definitions for all
    registered ``!commands``.  It can call tools, get real results, and
    iterate until it produces a final text answer.

    Write and destructive tool calls are gated behind user confirmation
    via ``/execute/resume`` (human-in-the-loop).  READ-level commands
    pass through without confirmation.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    # Load and expand
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

    # Check provider
    provider = get_provider()
    if not provider.is_available():
        return {
            "type": "status",
            "title": f"/*{name}",
            "data": {
                "message": "LLM not configured. Use !llm configure or set up a provider in Settings."
            },
        }

    # Build messages: system prompt + expanded template as user message
    base_prompt = load_system_prompt()
    messages: list[dict] = [
        {"role": "system", "content": base_prompt},
        {"role": "user", "content": expanded},
    ]

    # Parse tool domain declaration from template (# +tools: ...)
    allowed_domains = _parse_tool_domains(cmd.template)

    defs = get_definitions()
    defs = _filter_defs_by_domain(defs, allowed_domains)
    tools = defs_to_tools(defs) if defs else []

    # Run the multi-round tool loop
    result = await run_tool_loop(
        messages=messages,
        tools=tools,
        name=f"/{name}",
        provider=provider,
        dispatch_fn=_dispatch_path,
        get_handler_metadata_fn=get_handler_metadata,
        get_command_level_fn=get_command_level,
    )

    # Handle confirm_tool pause
    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    reply = result if isinstance(result, str) and result.strip() else None
    if reply:
        return {
            "type": "chat",
            "title": f"/*{name}",
            "data": {"html": render_markdown(reply), "actions": []},
        }

    return {
        "type": "chat",
        "title": f"/*{name}",
        "data": {"html": "<p><em>(empty response)</em></p>", "actions": []},
    }


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


# ── POST /execute/stream (legacy) ────────────────────────────────────────────


@router.post("/execute/stream")
async def execute_stream_endpoint(data: dict[str, Any]) -> StreamingResponse:
    """Streaming variant of ``/execute`` (deprecated — no tool-calling).

    Retained for backward compatibility. Prefer the non-streaming
    ``/execute`` endpoint which provides full tool-calling.
    """
    import json

    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    from pathlib import Path
    cmd = load_prompt_command(Path(_commands_dir()), name)

    async def event_stream():
        if cmd is None:
            available = [c.name for c in list_prompt_commands(Path(_commands_dir()))]
            msg = (
                f"Prompt command '{name}' not found. "
                f"Available: {', '.join(available) or '(none)'}"
            )
            yield f"data: {json.dumps({'token': msg})}\n\n"
            yield "data: [DONE]\n\n"
            return

        expanded = expand_prompt_template(cmd.template, args)

        provider = get_provider()
        if not provider.is_available():
            yield f"data: {json.dumps({'token': 'LLM not configured.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            base_prompt = load_system_prompt()
            stream_messages: list[dict] = [{"role": "system", "content": base_prompt}]
            stream_messages.append({"role": "user", "content": expanded})
            core = _create_core_provider(provider.config)
            result = await core.chat(stream_messages, stream=True)
            if hasattr(result, "__aiter__"):
                async for token in result:
                    yield f"data: {json.dumps({'token': token})}\n\n"
            else:
                yield f"data: {json.dumps({'token': str(result)})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'token': f'Error: {exc}'})}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
