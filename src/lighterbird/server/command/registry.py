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


def _resolve_user_aliases(
    tokens: list[str],
    flags: dict[str, str],
) -> tuple[list[str], dict[str, str]]:
    """Expand user-defined saved commands (``!ronzz INBOX`` → ``!email list --folder …``).

    Runs before built-in alias resolution so user aliases take priority
    (by design — the user explicitly created them).

    Args:
        tokens: Command tokens from the frontend.
        flags: Flag dict from the frontend.

    Returns:
        ``(tokens, flags)`` — possibly expanded if the first token matched
        a user alias.
    """
    try:
        from lighterbird.server.deps import get_user_commands_service

        svc = get_user_commands_service()
    except Exception:
        return tokens, flags  # graceful degradation

    result = svc.resolve_and_expand(tokens)
    if result is None:
        return tokens, flags

    new_tokens, new_flags = result
    # Merge: caller's explicit flags override expanded template flags
    merged = {**new_flags, **flags}
    return new_tokens, merged


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
    tokens, flags = _resolve_user_aliases(tokens, flags)
    resolved = _resolve_aliases(tokens)

    # Try from full path down to single token
    for i in range(len(resolved), 0, -1):
        key = ".".join(resolved[:i])
        handler = _commands.get(key)
        if handler is not None:
            remaining = resolved[i:]
            # If no remaining tokens, check if the tree node wants to
            # redirect to a default action (e.g. "email" → "email list").
            if not remaining:
                path_tokens = resolved[:i]
                try:
                    from lighterbird.server.command.tree import find_tree_node
                    node = find_tree_node(path_tokens)
                    if node and "default_action" in node:
                        # Redirect to the default action's handler
                        return dispatch(
                            path_tokens + [node["default_action"]],
                            flags,
                        )
                except Exception:
                    pass  # Gracefully fall through on any error
            return handler(remaining, flags)

    raise CommandNotFound(tokens)


def get_definitions() -> list[dict]:
    """Return command definitions for LLM tool schema.

    Generated from the authoritative command tree so that every
    flag and parameter is automatically available to the LLM.

    Returns a list of dicts, each with:
        - ``path``: token list (e.g. ``["email", "send"]``)
        - ``canonical``: string form (e.g. ``"!email send"``)
        - ``description``: human-readable help text
        - ``params``: optional list of param definitions
        - ``flags``: optional list of flag definitions
    """
    from lighterbird.server.command.tree import get_command_tree

    definitions: list[dict] = []

    def _walk(nodes: list[dict], prefix: list[str] | None = None) -> None:
        for node in nodes:
            path = (prefix or []) + [node["name"]]
            entry: dict = {
                "path": path,
                "canonical": f"!{' '.join(path)}",
            }
            desc = node.get("description")
            if desc:
                entry["description"] = desc

            flags = node.get("flags")
            if flags:
                entry["flags"] = [
                    {"name": f["name"], "type": f.get("type", "string"),
                     "help": f.get("help", "")}
                    for f in flags
                ]

            params = node.get("params")
            if params:
                entry["params"] = [
                    {"name": p["name"], "required": p.get("required", False),
                     "type": p.get("type", "string")}
                    for p in params
                ]

            definitions.append(entry)

            children = node.get("children")
            if children:
                _walk(children, path)

    _walk(get_command_tree())
    return definitions
