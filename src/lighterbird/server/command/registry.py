"""Decorator-based command registry and dispatch.

Usage::

    @command("email.list")
    def email_list(remaining: list[str], flags: dict[str, str]) -> dict:
        ...

    @alias("inbox", ["email", "list"])
    def _noop():
        ...

Then::

    dispatch(["email", "list"], {})  # calls email_list([], {})
    dispatch(["inbox"], {})           # resolves alias → calls email_list([], {})
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from lighterbird.server.command.errors import CommandNotFound

# (command_path: "email.list") → handler
_commands: dict[str, Callable[[list[str], dict[str, str]], dict[str, Any]]] = {}

# (aliased_path: "inbox") → canonical tokens: ["email", "list"]
_aliases: dict[str, list[str]] = {}


def command(path: str) -> Callable:
    """Register a command handler.

    The handler receives ``(remaining_tokens, flags)`` where
    ``remaining_tokens`` are the positional arguments after the
    command path, and returns a dict with at least a ``"type"`` key.

    Args:
        path: Dot-separated command path, e.g. ``"email.list"``.
    """

    def wrapper(
        fn: Callable[[list[str], dict[str, str]], dict[str, Any]],
    ) -> Callable:
        _commands[path] = fn
        return fn

    return wrapper


def alias(old_tokens: list[str], new_tokens: list[str]) -> None:
    """Register a backward-compatible command alias.

    When a user types the old command (e.g. ``["inbox"]``), it is
    transparently redirected to the new canonical command
    (e.g. ``["email", "list"]``).

    Args:
        old_tokens: Old command path as a list of tokens.
        new_tokens: Canonical command path as a list of tokens.
    """
    _aliases[".".join(old_tokens)] = new_tokens


def _resolve_aliases(tokens: list[str]) -> list[str]:
    """Resolve backward-compat aliases."""
    key = ".".join(tokens)
    while key in _aliases:
        tokens = _aliases[key]
        key = ".".join(tokens)
    return tokens


def dispatch(
    tokens: list[str],
    flags: dict[str, str],
) -> dict[str, Any]:
    """Resolve a command path and execute the matching handler.

    Args:
        tokens: Tokenised command path + positional args, e.g.
            ``["email", "list"]``.
        flags: Flag arguments keyed by name.

    Returns:
        Structured response dict with at least ``"type"``, ``"title"``,
        and ``"data"`` keys.

    Raises:
        CommandNotFound: If no handler matches the path.
    """
    resolved = _resolve_aliases(tokens)

    # Try from full path down to single token
    for i in range(len(resolved), 0, -1):
        key = ".".join(resolved[:i])
        handler = _commands.get(key)
        if handler is not None:
            remaining = resolved[i:]
            return handler(remaining, flags)

    raise CommandNotFound(tokens)


def get_definitions() -> list[dict]:
    """Return registered command definitions for LLM tool schema."""
    definitions: list[dict] = []
    for path, handler in _commands.items():
        parts = path.split(".")
        definitions.append({
            "path": parts,
            "canonical": f"!{' '.join(parts)}",
        })
    # Add aliases
    for alias_path, canonical in _aliases.items():
        definitions.append({
            "path": alias_path.split("."),
            "canonical": f"!{' '.join(canonical)}",
            "alias": True,
        })
    return definitions
