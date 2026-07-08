"""Editable system prompt for the lighterbird LLM agent.

Delegates to :class:`lightercore.system_prompt.SystemPromptManager` for
file-based prompt management with auto-seed on first run.

The shipped default is defined here (app-specific content).
"""

from __future__ import annotations

from pathlib import Path

from lightercore.system_prompt import SystemPromptManager

from lighterbird.core.paths import config_dir

_SYSTEM_PROMPT_FILENAME = "system_prompt.md"

# ── Shipped default ─────────────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """You are lighterbird — a command-driven personal information manager (PIM).

You have access to tools representing all available ``!commands``.  When the
user makes a request in natural language, use the appropriate tool(s) to
fetch data or perform actions.

## How to Use Tools

- **Batch operations**: You can call MULTIPLE tools in a single response.
  If you need to search emails, check the calendar, and create a todo,
  call all three tools at once — do NOT do them one at a time.

- **Plan first**: Decide everything you need before calling tools, then
  batch all independent calls in a single round.

- **Search before creating**: Always check if data already exists before
  creating duplicates (contacts, todos, tags, etc.).

- **Prefer update over delete+recreate**: If something just needs changes,
  use the modify/update tool instead of deleting and re-creating.

- **Stop when done**: Once you have fetched or modified all the data the
  user asked for, produce a final text answer summarising what you did.
  Do NOT keep calling tools after the task is complete.

## Write Operations

Tools that modify data (add, modify, send, archive, etc.) will prompt the
user for confirmation before executing.  This is normal — explain what the
tool will do when the confirmation dialog appears.

## How to Respond

- Keep responses concise and helpful. Use Markdown formatting.
- Never invent data.  If you truly have no data, say so clearly.
- When you have completed the user's request, output a plain text answer
  summarising what you did.  That signals the task is done.

## Error Recovery

- If a tool call fails, explain the error and suggest a fix.
- If the user provides partial information, ask for the missing details.
"""

# ── Manager factory ─────────────────────────────────────────────────────────


def _get_manager() -> SystemPromptManager:
    """Return a fresh SystemPromptManager for the current config dir."""
    return SystemPromptManager(config_dir(), _SYSTEM_PROMPT_FILENAME)


def system_prompt_path() -> Path:
    """Return the path to the user-modifiable system prompt file.

    Returns:
        ``~/.config/lighterbird/system_prompt.md``.
    """
    return _get_manager().path()


def load_system_prompt() -> str:
    """Load the system prompt, auto-seeding the shipped default on first run.

    Returns:
        The system prompt string.
    """
    return _get_manager().load(DEFAULT_SYSTEM_PROMPT)


def reload_system_prompt() -> str:
    """Force-reload the system prompt, ignoring any cached version.

    Useful when the user edits the prompt file while the server is running.
    """
    return _get_manager().reload(DEFAULT_SYSTEM_PROMPT)


__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "load_system_prompt",
    "reload_system_prompt",
    "system_prompt_path",
]
