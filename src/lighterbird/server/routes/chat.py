"""Chat API route — natural language interface.

``POST /api/v1/chat`` — Accepts natural language, optionally generates
a command via LLM tool-calling and executes it via the command dispatcher.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from lighterbird.server.command.models import CommandResponse
from lighterbird.server.command.registry import dispatch, get_definitions
from lighterbird.server.llm.provider import get_provider

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=CommandResponse)
async def chat_endpoint(data: dict[str, Any]) -> dict[str, Any]:
    """Accept a natural language message and return a response.

    If the LLM is available and configured, it will attempt to parse
    the user's intent into a structured command. Otherwise returns a
    placeholder message.
    """
    message = data.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required.")

    provider = get_provider()
    if not provider.is_available():
        return {
            "type": "status",
            "title": "LLM Chat",
            "data": {"message": "LLM mode coming in v0.2. Use ! commands for now."},
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

    # Fall back to plain chat
    response = await provider.chat(message)
    return {
        "type": "status",
        "title": "LLM Chat",
        "data": {"message": response},
    }
