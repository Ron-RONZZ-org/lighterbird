"""API routes for file-based prompt commands (/* prefix).

Provides three endpoints:
- GET  /api/v1/prompt-commands/list      — autocomplete source
- POST /api/v1/prompt-commands/expand    — preview expanded template
- POST /api/v1/prompt-commands/execute   — expand + send to LLM (sync JSON)

The execute endpoint returns the same JSON format as ``POST /api/v1/chat``
so the frontend can render it in a chat tab without special handling.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from lightercore.paths import config_dir
from lightercore.prompt_commands import (
    expand_prompt_template,
    list_prompt_commands,
    load_prompt_command,
)
from lighterbird.core.ai import get_provider as _create_core_provider
from lighterbird.server.llm.provider import get_provider
from lighterbird.server.llm.render import render_markdown

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

    Request body::

        {"name": "weekly", "args": ["INBOX"]}

    Response::

        {
            "name": "weekly",
            "description": "Weekly status report",
            "template": "Compile report from $1 folder.",
            "expanded": "Compile report from INBOX folder.",
            "param_count": 1
        }

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
    """Expand a prompt command and send the result to the LLM.

    Returns the same JSON format as ``POST /api/v1/chat``::

        {
            "type": "chat",
            "title": "/*weekly",
            "data": {"html": "...", "actions": []}
        }

    Request body::

        {"name": "weekly", "args": ["INBOX"]}

    Returns 404 if the command file does not exist.
    Returns 503 with a helpful message if no LLM provider is configured.
    """
    name = data.get("name", "").strip()
    args = data.get("args", [])

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")

    # 1. Load and expand
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

    # 2. Check LLM provider
    provider = get_provider()
    if not provider.is_available():
        return {
            "type": "status",
            "title": f"/*{name}",
            "data": {
                "message": (
                    "LLM not configured. "
                    "Use !llm configure or set up a provider in Settings."
                ),
            },
        }

    # 3. Send to LLM
    core = _create_core_provider(provider.config)
    messages = _build_prompt_messages(expanded)
    try:
        response = await core.chat(messages)
    except Exception as exc:
        from lightercore.exceptions import AIError
        if isinstance(exc, AIError):
            logger.warning("Prompt command /*%s AI error: %s", name, exc)
        else:
            logger.exception("Prompt command /*%s LLM call failed", name)
        return {
            "type": "status",
            "title": f"/*{name}",
            "data": {
                "message": f"LLM call failed: {exc}",
            },
        }

    if isinstance(response, str) and response.strip():
        html = render_markdown(response.strip())
        return {
            "type": "chat",
            "title": f"/*{name}",
            "data": {"html": html, "actions": []},
        }

    return {
        "type": "chat",
        "title": f"/*{name}",
        "data": {"html": "<p><em>(empty response)</em></p>", "actions": []},
    }


# ── POST /execute/stream (SSE) ───────────────────────────────────────────────


@router.post("/execute/stream")
async def execute_stream_endpoint(data: dict[str, Any]) -> StreamingResponse:
    """Streaming variant of ``/execute`` — returns SSE.

    Streams tokens as ``data: {"token": "..."}`` events, terminated by
    ``data: [DONE]`` — same format as ``POST /api/v1/chat/stream``.

    Request body::

        {"name": "weekly", "args": ["INBOX"]}
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
            yield f"data: {json.dumps({'token': 'LLM not configured. Use !llm configure or set up a provider in Settings.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            messages = _build_prompt_messages(expanded)
            core = _create_core_provider(provider.config)
            result = await core.chat(messages, stream=True)
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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Message builder ──────────────────────────────────────────────────────────


def _build_prompt_messages(expanded: str) -> list[dict]:
    """Build a minimal messages list for the LLM from an expanded prompt.

    Unlike regular chat (which injects system prompt + command definitions),
    prompt commands are just user messages — the user intentionally wrote
    the prompt, so we send it as-is without extra instructions.
    """
    from lighterbird.core.system_prompt import load_system_prompt

    system = load_system_prompt()
    if system.strip():
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": expanded},
        ]
    return [{"role": "user", "content": expanded}]
