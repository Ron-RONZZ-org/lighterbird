"""Chat API route — natural language interface with SSE streaming.

``POST /api/v1/chat`` — Standard response (single message).
``POST /api/v1/chat/stream`` — SSE streaming response for LLM output.

LLM configuration endpoints moved to ``routes/llm.py``.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from lighterbird.server.command.models import CommandResponse
from lighterbird.server.command.registry import dispatch, get_definitions
from lighterbird.server.llm.provider import get_provider
from lighterbird.server.llm.render import render_markdown, render_streaming_markdown

router = APIRouter(prefix="/api/v1", tags=["chat"])


def _build_messages(
    user_message: str = "",
    *,
    context: list[dict] | None = None,
    system_extra: str = "",
) -> list[dict]:
    """Build a chat messages list with dynamic command definitions injected.

    The authoritative command list is always from :func:`get_definitions`
    — the user's ``system_prompt.md`` is **not** loaded here because it
    may contain a stale ``AVAILABLE COMMANDS`` section. Users can still
    edit ``system_prompt.md`` for behavioural instructions; those are
    picked up by ``generate_command()`` in Phase 1.

    Args:
        user_message: The current user input. If empty, only the
            ``system_extra`` content is used as the user message (for
            Phase 2 summarization).
        context: Optional conversation history
            ``[{"role": "user"|"assistant", "content": "..."}]``.
        system_extra: Additional context appended to the user message
            (used in Phase 2 to describe the command result).

    Returns:
        List of message dicts suitable for ``provider.chat()``.
    """
    defs = get_definitions()
    defs_text = json.dumps(defs, indent=2) if defs else "[]"

    system_content = (
        "You are lighterbird — a command-driven personal information manager (PIM).\n\n"
        "When the user asks a question in natural language, check the AVAILABLE "
        "COMMANDS below. If a command matches, tell the user to run it (e.g. "
        "!backup list) or offer to execute it if you have the required details.\n\n"
        "AVAILABLE COMMANDS:\n"
        + defs_text
    )

    messages: list[dict] = [{"role": "system", "content": system_content}]

    if context:
        messages.extend(context)

    if system_extra:
        messages.append({"role": "user", "content": system_extra})
    elif user_message:
        messages.append({"role": "user", "content": user_message})

    return messages


@router.post("/chat", response_model=CommandResponse)
async def chat_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Accept a natural language message.

    Flow:
    1. Ask the LLM to parse the user's intent into a structured command.
    2. If a command is generated → execute it, send the result to the
       LLM for a natural-language summary, and return that summary.
    3. If the LLM can't generate a command, just return its response.

    Request body accepts:
        - ``message``: User message string.
        - ``context``: Optional list of previous messages
          ``[{"role": "user"|"assistant", "content": "..."}]``.
    """
    message = data.get("message", "").strip()
    context = data.get("context", None)
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    provider = get_provider()
    if not provider.is_available():
        return {
            "type": "status",
            "title": "LLM Chat",
            "data": {"message": "LLM not configured. Use ! commands or configure a provider."},
        }

    # ── Phase 1: Try to parse into a command ────────────────────────────
    defs = get_definitions()
    cmd = await provider.generate_command(message, defs)

    if cmd and cmd.get("tokens"):
        # Execute the command
        try:
            raw_result = dispatch(cmd["tokens"], cmd.get("flags", {}))
        except Exception as exc:
            return {
                "type": "status",
                "title": "LLM Chat",
                "data": {
                    "message": f"I understood your request but couldn't execute it: {exc}",
                    "original": message,
                },
            }

        # ── Phase 2: Summarize the result with the LLM ─────────────────
        import json as _json

        result_summary = _json.dumps(raw_result.get("data", raw_result), indent=2, default=str)
        summary_messages = _build_messages(
            system_extra=(
                f"The user's request was: '{message}'\n"
                f"You executed: !{' '.join(cmd['tokens'])}\n"
                f"Result:\n{result_summary}\n\n"
                f"Please summarize the result for the user in a helpful, "
                f"friendly way. Be concise but include all relevant details. "
                f"Use natural language, not JSON."
            ),
        )
        summary = await provider.chat(summary_messages)
        if isinstance(summary, str) and summary.strip():
            return {
                "type": "chat",
                "title": "LLM Chat",
                "data": {"html": render_markdown(summary.strip()), "actions": []},
            }
        # Fallback: return raw result if LLM summarization fails
        return raw_result

    # ── Phase 3: No command — respond as plain chat ───────────────────
    messages = _build_messages(message, context=context)
    response = await provider.chat(messages)
    if isinstance(response, str):
        html = render_markdown(response)
        return {
            "type": "chat",
            "title": "LLM Chat",
            "data": {"html": html, "actions": []},
        }
    return {
        "type": "chat",
        "title": "LLM Chat",
        "data": {"html": "<p>LLM response unavailable.</p>", "actions": []},
    }


@router.post("/chat/stream")
async def chat_stream(data: dict[str, Any]) -> StreamingResponse:
    """SSE streaming endpoint for LLM chat.

    Returns a ``text/event-stream`` response with tokens sent as
    ``data: {"token": "..."}`` events, terminated by ``data: [DONE]``.

    Request body accepts:
        - ``message``: User message string.
        - ``context``: Optional list of previous messages.
    """
    message = data.get("message", "").strip()
    context = data.get("context", None)
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    provider = get_provider()

    async def event_stream():
        if not provider.is_available():
            yield f"data: {json.dumps({'token': 'LLM not configured. Use ! commands or configure a provider.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            stream_messages = _build_messages(message, context=context)
            result = await provider.chat(stream_messages, stream=True)
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


# (LLM configuration endpoints moved to routes/llm.py)
