"""Chat API route — natural language interface with SSE streaming.

``POST /api/v1/chat`` — Standard response (single message).
``POST /api/v1/chat/stream`` — SSE streaming response for LLM output.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from lighterbird.server.command.models import CommandResponse
from lighterbird.server.command.registry import dispatch, get_definitions
from lighterbird.server.llm.provider import get_provider

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=CommandResponse)
async def chat_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Accept a natural language message and return a structured response.

    If the LLM is available and configured, it will attempt to parse
    the user's intent into a structured command. Otherwise returns a
    fallback message.
    """
    message = data.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    provider = get_provider()
    if not provider.is_available():
        return {
            "type": "status",
            "title": "LLM Chat",
            "data": {"message": "LLM not configured. Use ! commands or configure a provider."},
        }

    # Attempt to generate a command from the natural language
    defs = get_definitions()
    cmd = await provider.generate_command(message, defs)

    if cmd and cmd.get("tokens"):
        try:
            result = dispatch(cmd["tokens"], cmd.get("flags", {}))
            return {
                "type": result.get("type", "status"),
                "title": result.get("title", ""),
                "data": result.get("data", result),
            }
        except Exception as exc:
            return {
                "type": "status",
                "title": "LLM Chat",
                "data": {
                    "message": f"I understood your request but couldn't execute it: {exc}",
                    "original": message,
                },
            }

    # Fall back to plain chat (non-streaming)
    response = await provider.chat(message)
    if isinstance(response, str):
        return {
            "type": "status",
            "title": "LLM Chat",
            "data": {"message": response},
        }
    return {
        "type": "status",
        "title": "LLM Chat",
        "data": {"message": "LLM response unavailable."},
    }


@router.post("/chat/stream")
async def chat_stream(data: dict[str, Any]) -> StreamingResponse:
    """SSE streaming endpoint for LLM chat.

    Returns a ``text/event-stream`` response with tokens sent as
    ``data: {"token": "..."}`` events, terminated by ``data: [DONE]``.
    """
    message = data.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    provider = get_provider()

    async def event_stream():
        if not provider.is_available():
            yield f"data: {json.dumps({'token': 'LLM not configured. Use ! commands or configure a provider.'})}\n\n"
            yield "data: [DONE]\n\n"
            return

        try:
            result = await provider.chat(message, stream=True)
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
