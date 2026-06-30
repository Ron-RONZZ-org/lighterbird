"""Command dispatch API route.

``POST /api/v1/command`` — Execute a parsed command and return a structured response.
``GET /api/v1/command/definitions`` — Return the command tree for autocomplete / LLM tool schema.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from lighterbird.server.command.errors import CommandError, CommandNotFound, CommandValidationError
from lighterbird.server.command.models import CommandRequest, CommandResponse
from lighterbird.server.command.registry import dispatch, get_definitions
from lighterbird.server.command.tree import get_command_tree

router = APIRouter(prefix="/api/v1", tags=["command"])

# ── Interactive command form mapping ──────────────────────────────────────
# Maps a command path (dotted) to its form type string.
_INTERACTIVE_FORMS: dict[str, str] = {
    "email.send": "email-send",
    "email.sieve.add": "email-sieve-add",
    "email.sieve.modify": "email-sieve-modify",
    "calendar.event.add": "calendar-event-add",
    "contact.add": "contacts-add",
    "contact.modify": "contacts-modify",
    "email.account.add": "email-account-add",
    "email.account.modify": "email-account-modify",
    "calendar.account.add": "calendar-account-add",
    "calendar.account.modify": "calendar-account-modify",
    "todo.add": "todo-add",
    "todo.modify": "todo-modify",
    "todo.template.add": "todo-template-add",
    "todo.template.modify": "todo-template-modify",
    "journal.write": "journal-write",
    "user.saved-commands.add": "user-saved-commands-add",
    "user.saved-commands.modify": "user-saved-commands-modify",
    "user.info.add": "user-info-add",
    "user.info.modify": "user-info-modify",
    "llm.profile.new": "llm-profile-new",
    "llm.profile.set": "llm-profile-set",
    "backup.config.add": "backup-config-add",
    "backup.config.modify": "backup-config-modify",
    "backup.prune": "backup-prune",
    "sync": "sync",
    "letter.add": "letter-add",
    "letter.send": "letter-send",
    "todo.delete": "todo-delete",
    "todo.template.delete": "todo-template-delete",
    "email.account.delete": "email-account-delete",
    "calendar.event.delete": "calendar-event-delete",
    "calendar.account.delete": "calendar-account-delete",
    "backup.config.delete": "backup-config-delete",
    "user.saved-commands.delete": "user-saved-commands-delete",
}


def _resolve_form_type(tokens: list[str]) -> str | None:
    """Check if the given command path maps to an interactive form.

    Tries progressively shorter paths (full path down to 2 tokens)
    to find a match.
    """
    for i in range(len(tokens), 1, -1):
        key = ".".join(tokens[:i])
        if key in _INTERACTIVE_FORMS:
            return _INTERACTIVE_FORMS[key]
    return None


def _extract_partial_data(tokens: list[str], flags: dict[str, str]) -> dict[str, str]:
    """Extract whatever the user has already typed as initial form data.

    Positional args after the command path become param values.
    Flag values become form field values.
    """
    data: dict[str, str] = {}

    # Find where the command path ends and positional args begin
    from lighterbird.server.command.tree import _find_command_depth

    cmd_depth = _find_command_depth(tokens)
    if cmd_depth < len(tokens):
        params = tokens[cmd_depth:]
        # Map param names from the tree
        key = ".".join(tokens[:cmd_depth]) if cmd_depth > 0 else ""
        if key in _INTERACTIVE_FORMS:
            from lighterbird.server.command.tree import _get_param_names
            names = _get_param_names(tokens[:cmd_depth])
            for i, val in enumerate(params):
                if i < len(names):
                    data[names[i]] = val
                else:
                    break

    # Flag values (skip meta-flags like --form)
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
            form_type = _resolve_form_type(req.tokens)
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
        form_type = _resolve_form_type(req.tokens)
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
