"""Command dispatch API route.

``POST /api/v1/command`` — Execute a parsed command and return a structured response.
``GET /api/v1/command/definitions`` — Return the command tree for autocomplete / LLM tool schema.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from lighterbird.server.command.errors import (
    CommandError,
    CommandNotFound,
    CommandValidationError,
)
from lighterbird.server.command.models import CommandRequest, CommandResponse
from lighterbird.server.command.registry import (
    dispatch,
    get_definitions,
    resolve_form_type,
)
from lighterbird.server.command.tree import (
    find_command_depth,
    get_command_tree,
    get_param_names,
)

router = APIRouter(prefix="/api/v1", tags=["command"])


def _extract_partial_data(tokens: list[str], flags: dict[str, str]) -> dict[str, str]:
    """Extract whatever the user has already typed as initial form data."""
    data: dict[str, str] = {}
    cmd_depth = find_command_depth(tokens)
    if cmd_depth < len(tokens):
        params = tokens[cmd_depth:]
        ".".join(tokens[:cmd_depth]) if cmd_depth > 0 else ""
        if resolve_form_type(tokens[:cmd_depth]):
            names = get_param_names(tokens[:cmd_depth])
            for i, val in enumerate(params):
                if i < len(names):
                    data[names[i]] = val
                else:
                    break
    for k, v in flags.items():
        if k == "form":
            continue
        if v:
            data[k] = v
    return data


@router.post("/command", response_model=CommandResponse)
def execute_command(req: CommandRequest) -> dict[str, Any]:
    """Execute a parsed command and return structured output.

    The frontend sends tokenised input; the backend resolves the command
    path, runs the registered handler, and returns the result.

    For interactive commands where the handler raises CommandValidationError
    (missing/invalid args), this automatically returns a ``form-required``
    response so the frontend can open an interactive form with pre-filled data.
    """
    try:
        # --form flag: skip dispatch, return form-required immediately
        if "form" in req.flags:
            form_type = resolve_form_type(req.tokens)
            if form_type:
                return {
                    "type": "form-required",
                    "title": f"Complete {form_type.replace('-', ' ').title()}",
                    "data": {
                        "form": form_type,
                        "initialData": _extract_partial_data(req.tokens, req.flags),
                    },
                }

        result = dispatch(req.tokens, req.flags)
        # Ensure type/title/data keys exist
        return {
            "type": result.get("type", "status"),
            "title": result.get("title", ""),
            "data": result.get("data", result),
        }
    except CommandNotFound as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CommandValidationError as e:
        # If the failed command has an interactive form, return form-required
        form_type = resolve_form_type(req.tokens)
        if form_type:
            return {
                "type": "form-required",
                "title": f"Complete {form_type.replace('-', ' ').title()}",
                "data": {
                    "form": form_type,
                    "initialData": _extract_partial_data(req.tokens, req.flags),
                    "message": str(e),
                },
            }
        # Fall back to standard error response
        raise HTTPException(
            status_code=400,
            detail={"error": str(e), "suggestion": getattr(e, "suggestion", "")},
        )
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


@router.get("/command/tree")
def command_tree() -> list[dict]:
    """Return the full structured command tree for frontend autocomplete.

    Each node contains name, description, children, params, flags, and
    interactive flag for the command hierarchy. This is fetched dynamically
    on frontend startup to keep autocomplete in sync with backend commands.
    """
    return get_command_tree()
