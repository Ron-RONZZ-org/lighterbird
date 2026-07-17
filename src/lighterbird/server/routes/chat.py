"""Chat API route — multi-round tool-calling LLM chat.

``POST  /api/v1/chat``         — Send a message; LLM uses tools iteratively.
``POST  /api/v1/chat/resume``  — Resume a paused HITL session.
``POST  /api/v1/chat/stream``  — (Deprecated) SSE streaming without tools.
``GET   /api/v1/chat/notice``  — Return stale-commands notice.

The primary endpoint (``/chat``) runs a **multi-round tool-calling loop**
using the LLM tool registry (:mod:`~lighterbird.server.llm.tools`).
The LLM receives **AI-optimised tools** (domain services called directly,
UUID-based operations, structured schemas) and can call them, see
results, and iterate until it produces a final answer.  WRITE-level tools
gate behind user confirmation via ``/chat/resume``.

Unlike the CLI command registry (which serves human ``!`` commands), the
LLM tool registry is a separate set of tools designed for AI consumption —
no CLI flag parsing overhead, no frontend-shaped response wrapping.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from lightercore.permissions import PermissionLevel

from lighterbird.core.ai import get_provider as _create_core_provider
from lighterbird.core.system_prompt import load_system_prompt
from lighterbird.server.command.registry import (
    get_definitions as _get_cli_definitions,  # used only by legacy /chat/stream
    get_handler_metadata as _get_cli_handler_metadata,
)
from lighterbird.server.llm.provider import get_provider
from lighterbird.server.llm.render import render_markdown
from lighterbird.server.llm.tool_loop import (
    _pending_executions,
    resume_execution,
    run_tool_loop,
)
from lighterbird.server.llm.tools import (
    dispatch_llm_tool,
    get_llm_tool_level,
    get_llm_tool_metadata,
    get_llm_tools,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["chat"])

# Matches any ``!command`` mention in system_prompt.md — used to detect a
# stale manual command listing and show a dismissible notice.
_COMMAND_LISTING_RE = re.compile(r"![a-z][\w-]*")


# ── Notice system (dismissible banner) ────────────────────────────────────


def _check_notice() -> dict | None:
    """Check if system_prompt.md mentions any ``!command`` and return notice data."""
    base_prompt = load_system_prompt()
    if not _COMMAND_LISTING_RE.search(base_prompt):
        return None
    logger.info("system_prompt.md mentions !commands — showing dismissible notice.")
    return {
        "id": "stale-commands",
        "message": (
            "\u2139\ufe0f Your ``system_prompt.md`` mentions specific ``!`` "
            "commands. The authoritative, up-to-date command list is "
            "auto-injected into the LLM context via tool definitions. "
            "You can safely remove the manual tool-usage instructions."
        ),
    }


def _with_notice(response: dict) -> dict:
    """Attach a ``_notice`` field if a pending notice exists."""
    notice = _check_notice()
    if notice:
        response["_notice"] = notice
    return response


def _build_tool_messages(
    user_message: str,
    context: list[dict] | None = None,
) -> list[dict]:
    """Build messages for the tool loop: system prompt + conversation history.

    Tool definitions are supplied separately via
    :func:`~lighterbird.server.llm.tools.get_llm_tools` to the
    tool loop — they are NOT dumped as plain text.
    """
    base_prompt = load_system_prompt()
    messages: list[dict] = [{"role": "system", "content": base_prompt}]
    if context:
        messages.extend(context)
    messages.append({"role": "user", "content": user_message})
    return messages


def _dispatch_llm_tool(path: str, flags: dict) -> dict:
    """Dispatch an LLM tool by dot-separated path.

    Routes through the LLM tool registry (NOT the CLI command registry).
    LLM tools call domain services directly — no flag parsing overhead.
    """
    return dispatch_llm_tool(path, flags)


def _get_llm_tool_level(path: str) -> PermissionLevel | None:
    """Permission lookup for LLM tools only — no CLI registry fallback.

    Passed as ``get_tool_level_fn`` to :func:`run_tool_loop` and
    :func:`resume_execution`.
    """
    return get_llm_tool_level(path)


def _get_handler_metadata(path: str) -> dict | None:
    """Combined metadata lookup: LLM tool registry first, then CLI registry.

    The LLM tool registry stores ``description`` in its entries, which
    :func:`~lightercore.llm.tool_loop.run_tool_loop` uses to populate
    the ``confirm_tool`` dialog descriptions.
    """
    meta = get_llm_tool_metadata(path)
    if meta:
        return meta
    return _get_cli_handler_metadata(path)


# ── Primary chat endpoint ────────────────────────────────────────────────


@router.post("/chat")
async def chat_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Send a message and let the LLM use tools iteratively.

    Request body:
        ``message`` (str): User message.
        ``context`` (list[dict], optional): Conversation history.

    Returns:
        - ``{"type": "chat", "data": {"html": "..."}}`` on success.
        - ``{"type": "confirm_tool", ...}`` if write tools need approval.
        - ``{"type": "status", ...}`` if the provider is unavailable.
    """
    message = data.get("message", "").strip()
    context = data.get("context")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    provider = get_provider()
    if not provider.is_available():
        return {
            "type": "status",
            "title": "LLM Chat",
            "data": {"message": "LLM not configured. Use ! commands or configure a provider."},
        }

    # Build messages and tool definitions from the LLM tool registry
    messages = _build_tool_messages(message, context)
    tools = get_llm_tools()

    # Run the multi-round tool loop
    result = await run_tool_loop(
        messages=messages,
        tools=tools,
        name="chat",
        provider=provider,
        dispatch_fn=_dispatch_llm_tool,
        get_handler_metadata_fn=_get_handler_metadata,
        get_command_level_fn=lambda _: None,  # unused — get_tool_level_fn takes priority
        get_tool_level_fn=_get_llm_tool_level,
    )

    # Handle confirm_tool pause
    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    # Handle final text answer
    reply = result if isinstance(result, str) and result.strip() else None
    if reply:
        return _with_notice({
            "type": "chat",
            "title": "LLM Chat",
            "data": {"html": render_markdown(reply), "actions": []},
        })

    return _with_notice({
        "type": "chat",
        "title": "LLM Chat",
        "data": {"html": "<p><em>(empty response)</em></p>", "actions": []},
    })


# ── Resume (HITL) ────────────────────────────────────────────────────────


@router.post("/chat/resume")
async def chat_resume(data: dict[str, Any]) -> dict[str, Any]:
    """Resume a paused chat execution after user confirmation.

    Request body:
        ``session_id`` (str): Session UUID from the ``confirm_tool`` response.
        ``decisions`` (dict[int, bool], optional): Per-tool-index approval.
        ``confirmed`` (bool, optional): Blanket approve/reject all tools.

    Returns:
        Same response types as :func:`chat_endpoint`.
    """
    session_id = data.get("session_id", "")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required.")

    provider = get_provider()
    if not provider.is_available():
        return {
            "type": "status",
            "title": "LLM Chat",
            "data": {"message": "LLM not configured."},
        }

    try:
        result = await resume_execution(
            session_id=session_id,
            decisions=data.get("decisions"),
            confirmed=data.get("confirmed"),
            provider=provider,
            dispatch_fn=_dispatch_llm_tool,
            get_handler_metadata_fn=_get_handler_metadata,
            get_command_level_fn=lambda _: None,  # unused — get_tool_level_fn takes priority
            get_tool_level_fn=_get_llm_tool_level,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Handle confirm_tool pause (nested: LLM wants more approvals)
    if isinstance(result, dict) and result.get("type") == "confirm_tool":
        return result

    reply = result if isinstance(result, str) and result.strip() else None
    if reply:
        return _with_notice({
            "type": "chat",
            "title": "LLM Chat",
            "data": {"html": render_markdown(reply), "actions": []},
        })

    return _with_notice({
        "type": "chat",
        "title": "LLM Chat",
        "data": {"html": "<p><em>(command completed)</em></p>", "actions": []},
    })


# ── Legacy endpoints ─────────────────────────────────────────────────────


@router.get("/chat/notice")
def get_notice() -> dict:
    """Return the current notice (if any) for the frontend banner."""
    notice = _check_notice()
    return {"notice": notice}


@router.post("/chat/stream")
async def chat_stream(data: dict[str, Any]) -> StreamingResponse:
    """SSE streaming endpoint (deprecated — no tool-calling).

    Retained for backward compatibility.  Prefer using the non-streaming
    ``POST /api/v1/chat`` endpoint which provides full tool-calling.
    """
    message = data.get("message", "").strip()
    context = data.get("context")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    provider = get_provider()

    async def event_stream():
        if not provider.is_available():
            yield f"data: {json.dumps({'token': 'LLM not configured. Use ! commands or configure a provider.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            # Build messages with command definitions as text (legacy format)
            base_prompt = load_system_prompt()
            cli_defs = _get_cli_definitions()
            defs_text = json.dumps(cli_defs, indent=2) if cli_defs else "[]"
            system_content = base_prompt + "\n\nAVAILABLE COMMANDS:\n" + defs_text
            stream_messages: list[dict] = [{"role": "system", "content": system_content}]
            if context:
                stream_messages.extend(context)
            stream_messages.append({"role": "user", "content": message})

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
