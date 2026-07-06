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
