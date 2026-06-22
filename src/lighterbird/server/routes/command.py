"""Command dispatch API route.

``POST /api/v1/command`` — Execute a parsed command and return a structured response.
``GET /api/v1/command/definitions`` — Return the command tree for autocomplete / LLM tool schema.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from lighterbird.server.command.errors import CommandError, CommandNotFound
from lighterbird.server.command.models import CommandRequest, CommandResponse
from lighterbird.server.command.registry import dispatch, get_definitions

router = APIRouter(prefix="/api/v1", tags=["command"])


@router.post("/command", response_model=CommandResponse)
def execute_command(req: CommandRequest) -> dict[str, Any]:
    """Execute a parsed command and return structured output.

    The frontend sends tokenised input; the backend resolves the command
    path, runs the registered handler, and returns the result.
    """
    try:
        result = dispatch(req.tokens, req.flags)
        # Ensure type/title/data keys exist
        return {
            "type": result.get("type", "status"),
            "title": result.get("title", ""),
            "data": result.get("data", result),
        }
    except CommandNotFound as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CommandError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": str(e), "suggestion": getattr(e, "suggestion", "")},
        )


@router.get("/command/definitions")
def list_command_definitions() -> list[dict]:
    """Return all registered command definitions.

    Used by:
        - The frontend command tree (autocomplete)
        - The LLM tool-calling schema
    """
    return get_definitions()
