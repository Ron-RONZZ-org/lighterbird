"""Chat API route — multi-round tool-calling LLM chat.

``POST  /api/v1/chat``         — Send a message; LLM uses tools iteratively.
``POST  /api/v1/chat/resume``  — Resume a paused HITL session.
``POST  /api/v1/chat/stream``  — (Deprecated) SSE streaming without tools.
``GET   /api/v1/chat/notice``  — Return stale-commands notice.

The primary endpoint (``/chat``) replaces the old one-shot ``generate_command``
→ dispatch → summarise pipeline with a **multi-round tool-calling loop**.
The LLM receives all registered ``!commands`` as native tools and can
call them, see results, and iterate until it produces a final answer.
WRITE-level tools gate behind user confirmation via ``/chat/resume``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from lightercore.llm.base import defs_to_tools

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
    _pending_executions,
    resume_execution,
    run_tool_loop,
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

    Unlike the old ``_build_messages``, this does **not** dump command
    definitions as plain text — they are supplied as native tool
    definitions via :func:`defs_to_tools` instead.
    """
    base_prompt = load_system_prompt()
    messages: list[dict] = [{"role": "system", "content": base_prompt}]
    if context:
        messages.extend(context)
    messages.append({"role": "user", "content": user_message})
    return messages


def _dispatch_path(path: str, flags: dict) -> dict:
    """Dispatch a command by dot-separated path.

    Splits ``"email.list"`` → ``["email", "list"]`` and calls
    :func:`~lighterbird.server.command.registry.dispatch`.
    """
    return dispatch(path.split("."), flags)


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

    # Build messages and tool definitions
    messages = _build_tool_messages(message, context)
    defs = get_definitions()
    tools = defs_to_tools(defs) if defs else []

    # Run the multi-round tool loop
    result = await run_tool_loop(
        messages=messages,
        tools=tools,
        name="chat",
        provider=provider,
        dispatch_fn=_dispatch_path,
        get_handler_metadata_fn=get_handler_metadata,
        get_command_level_fn=get_command_level,
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
            dispatch_fn=_dispatch_path,
            get_handler_metadata_fn=get_handler_metadata,
            get_command_level_fn=get_command_level,
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
            defs_text = json.dumps(get_definitions(), indent=2) if get_definitions() else "[]"
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
