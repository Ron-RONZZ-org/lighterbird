"""Editable system prompt for the lighterbird LLM agent.

Users can customise the system prompt by placing a file at::

    ~/.config/lighterbird/system_prompt.md

On first run (when no file exists) a shipped default is automatically
copied to that location so the user can edit it.

Pattern inspired by A-kunpiloto's config.py.
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.paths import config_dir

_SYSTEM_PROMPT_FILENAME = "system_prompt.md"

# ── Shipped default ─────────────────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """You are lighterbird — a command-driven personal information manager (PIM).

You have access to the following commands. When the user makes a request in
natural language, convert it into the appropriate command.

AVAILABLE COMMANDS (also listed dynamically when the user asks about them):
- !help — Show all available commands and their usage
- !sync — Trigger all syncs
- !backup — Show backup subcommands
- !email — Show email subcommands
- !calendar — Show calendar subcommands
- !contacts — Show contacts subcommands
- !todo — Show todo subcommands
- !journal — Show journal subcommands
- !llm — Show LLM configuration subcommands

Each root command has subcommands. For the full, up-to-date list with
parameters and flags, tell the user to run ``!<command>`` (e.g. ``!backup``
to see backup subcommands) or ``!help``.

RULES:
1. When the user asks for an action, generate the appropriate !command.
2. Respond with the command result in a helpful, concise way.
3. If the user asks something not covered by commands, use your general knowledge.
4. Be concise. Use bullet points and tables where appropriate.
5. If you need more information (like a UUID or missing parameters), ask the user.

ERROR RECOVERY:
- If a command fails, explain the error and suggest a fix.
- If the user provides partial information, ask for the missing details.
"""


def _lighterbird_config_dir() -> Path:
    """Return the lighterbird config directory.

    Returns:
        ``~/.config/lighterbird/`` (XDG-compliant).
    """
    return config_dir()


def system_prompt_path() -> Path:
    """Return the path to the user-modifiable system prompt file.

    Returns:
        ``~/.config/lighterbird/system_prompt.md``.
    """
    return _lighterbird_config_dir() / _SYSTEM_PROMPT_FILENAME


def load_system_prompt() -> str:
    """Load the system prompt, auto-seeding the shipped default on first run.

    Resolution order:
    1. If ``~/.config/lighterbird/system_prompt.md`` exists and is
       non-empty → return its content (never modified).
    2. Otherwise, write the shipped default to that location and
       return its content.
    3. Fall back to :data:`DEFAULT_SYSTEM_PROMPT`.

    Returns:
        The system prompt string.
    """
    path = system_prompt_path()

    if path.exists():
        content = path.read_text(encoding="utf-8").strip()
        if content:
            return content

    # 2. Auto-seed on first run
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(DEFAULT_SYSTEM_PROMPT, encoding="utf-8")
    except OSError:
        pass  # Non-critical
    return DEFAULT_SYSTEM_PROMPT


def reload_system_prompt() -> str:
    """Force-reload the system prompt, ignoring any cached version.

    Useful when the user edits the prompt file while the server is running.
    """
    return load_system_prompt()


__all__ = [
    "DEFAULT_SYSTEM_PROMPT",
    "load_system_prompt",
    "reload_system_prompt",
    "system_prompt_path",
]
