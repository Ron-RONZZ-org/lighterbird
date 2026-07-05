"""Decorator-based command registry and dispatch with auto-generated command tree.

Usage::

    @command("email.list", description="Show inbox messages",
             params=[Param("limit", type="number", default=20)],
             flags=[Flag("folder", type="string")])
    def email_list(remaining: list[str], flags: dict[str, str]) -> dict:
        ...

    @group("email", description="Email operations", default_action="list")
    def _email_group():
        ...

    @alias("inbox", ["email", "list"])
    def _noop():
        ...

Then::

    dispatch(["email", "list"], {})   # calls email_list([], {})
    dispatch(["inbox"], {})            # resolves alias → calls email_list([], {})
    dispatch(["email"], {})            # default_action="list" → calls email_list([], {})

    get_command_tree()  # auto-generated from @command and @group registrations
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

from lighterbird.server.command.errors import CommandNotFound

# ── Data structures ───────────────────────────────────────────────────────

# (command_path: "email.list") → (handler_fn, metadata_dict)
_commands: dict[str, tuple[Callable, dict[str, Any]]] = {}

# (group_path: "email") → metadata dict (description, default_action, ...)
_group_metadata: dict[str, dict[str, Any]] = {}

# (aliased_path: "inbox") → canonical tokens: ["email", "list"]
_aliases: dict[str, list[str]] = {}

# (command_path: "email.send") → form type string: "email-send"
_interactive_forms: dict[str, str] = {}

# Command tree cache — invalidated whenever @command() or @group() is called.
# Avoids rebuilding the nested tree dict on every autocomplete keystroke.
_tree_cache: list[dict[str, Any]] | None = None
_tree_version: int = 0

# Flag to skip cache invalidation during initial bulk registration.
# Set to True while __init__.py imports all handler modules.
_bulk_loading: bool = False


def _invalidate_tree_cache() -> None:
    """Mark the command tree cache as stale."""
    global _tree_version, _tree_cache
    if not _bulk_loading:
        _tree_version += 1
        _tree_cache = None


# ── Decorators ────────────────────────────────────────────────────────────


def command(path: str, **metadata: Any) -> Callable:
    """Register a command handler with optional metadata.

    The handler receives ``(remaining_tokens, flags)`` where
    ``remaining_tokens`` are the positional arguments after the
    command path, and returns a dict with at least a ``"type"`` key.

    Args:
        path: Dot-separated command path, e.g. ``"email.list"``.
        **metadata: Optional metadata for auto-generated command tree.

    Recognized metadata keys:
        description: str — help text for autocomplete.
        params: list[dict] — positional params with keys name/type/required/default.
        flags: list[dict] — flag definitions with keys name/type/help/short.
        interactive: bool — whether this command has a form fallback.
        form_type: str — frontend form type (defaults to path with ``-``).
        default_action: str — subcommand to redirect to (group nodes only).
    """
    if metadata.get("interactive"):
        form_type = metadata.get("form_type", path.replace(".", "-"))
        _interactive_forms[path] = form_type

    def wrapper(fn: Callable) -> Callable:
        _commands[path] = (fn, metadata)
        _invalidate_tree_cache()
        return fn

    return wrapper


def group(path: str, **metadata: Any) -> Callable:
    """Register metadata for a non-leaf command group.

    Groups don't have their own handler, but they can have descriptions
    shown in autocomplete and a ``default_action`` that redirects to a
    subcommand when the user types just the group name (e.g. ``!email``
    → ``!email list``).

    Args:
        path: Dot-separated group path, e.g. ``"email"``.
        **metadata: Recognized keys: description, default_action.
    """
    _group_metadata[path] = metadata
    _invalidate_tree_cache()

    # Return a no-op decorator that does nothing (groups have no handler)
    def wrapper(fn: Callable | None = None) -> Callable:
        return fn  # type: ignore[return-value]

    return wrapper


def alias(old_tokens: list[str], new_tokens: list[str]) -> None:
    """Register a backward-compatible command alias.

    When a user types the old command (e.g. ``["inbox"]``), it is
    transparently redirected to the new canonical command
    (e.g. ``["email", "list"]``).
    """
    _aliases[".".join(old_tokens)] = new_tokens


# ── Alias resolution ──────────────────────────────────────────────────────


def _resolve_aliases(tokens: list[str]) -> list[str]:
    """Resolve backward-compat aliases.

    Uses a visited-set guard to detect circular alias chains
    (e.g. a → b → a) and break the loop.
    """
    seen: set[str] = set()
    key = ".".join(tokens)
    while key in _aliases:
        if key in seen:
            logger.error("Circular alias detected: %s is already in the resolution chain", key)
            break
        seen.add(key)
        tokens = _aliases[key]
        key = ".".join(tokens)
    return tokens


def _resolve_user_aliases(
    tokens: list[str],
    flags: dict[str, str],
) -> tuple[list[str], dict[str, str]]:
    """Expand user-defined saved commands (``!ronzz INBOX`` → ``!email list --folder …``).

    Runs before built-in alias resolution so user aliases take priority.
    """
    try:
        from lighterbird.server.deps import get_user_commands_service
        svc = get_user_commands_service()
    except (ImportError, RuntimeError, LookupError):
        return tokens, flags  # graceful degradation

    result = svc.resolve_and_expand(tokens)
    if result is None:
        return tokens, flags

    new_tokens, new_flags = result
    merged = {**new_flags, **flags}
    return new_tokens, merged


# ── Dispatch ──────────────────────────────────────────────────────────────


def dispatch(
    tokens: list[str],
    flags: dict[str, str],
) -> dict[str, Any]:
    """Resolve a command path and execute the matching handler.

    Args:
        tokens: Tokenised command path + positional args.
        flags: Flag arguments keyed by name.

    Returns:
        Structured response dict.

    Raises:
        CommandNotFound: If no handler matches the path.
    """
    tokens, flags = _resolve_user_aliases(tokens, flags)
    resolved = _resolve_aliases(tokens)

    for i in range(len(resolved), 0, -1):
        key = ".".join(resolved[:i])
        entry = _commands.get(key)
        if entry is not None:
            handler_fn, metadata = entry
            remaining = resolved[i:]

            # Inject positional params from remaining into flags
            params = metadata.get("params", [])
            for idx, val in enumerate(remaining):
                if idx < len(params):
                    pname = params[idx]["name"]
                    if pname not in flags:
                        flags[pname] = val
                else:
                    fname = f"_{idx}"
                    if fname not in flags:
                        flags[fname] = val

            # Check for default_action redirect (group with no subcommand).
            # Only redirect when the matched handler is the *exact* group,
            # not a subcommand — prevents infinite recursion.
            if not remaining:
                gkey = ".".join(resolved[:i])
                gmeta = _group_metadata.get(gkey)
                if gmeta and "default_action" in gmeta:
                    redirected = [*resolved[:i], gmeta["default_action"]]
                    if redirected != resolved:
                        return dispatch(redirected, flags)

            return handler_fn(remaining, flags)

    raise CommandNotFound(tokens)


# ── Auto-generated command tree ───────────────────────────────────────────


def get_command_tree() -> list[dict[str, Any]]:
    """Build the command tree from registered handlers and groups.

    The tree is auto-generated from ``@command()`` and ``@group()``
    decorator registrations, so it never goes out of sync with the
    available commands.

    The result is cached and invalidated automatically whenever
    a new command or group is registered, avoiding redundant rebuilds
    on every autocomplete keystroke.

    Returns:
        List of command node dicts suitable for frontend autocomplete.
    """
    global _tree_cache
    if _tree_cache is not None:
        return _tree_cache

    root: dict[str, Any] = {}

    # 1. Build tree structure from registered leaf commands
    for path_str, (_, meta) in _commands.items():
        parts = path_str.split(".")
        current = root
        for idx, part in enumerate(parts):
            is_last = idx == len(parts) - 1
            if part not in current:
                entry: dict[str, Any] = {"name": part}
                if is_last:
                    entry["description"] = meta.get("description", "")
                    if meta.get("params"):
                        entry["params"] = list(meta["params"])
                    if meta.get("flags"):
                        entry["flags"] = list(meta["flags"])
                    if meta.get("interactive"):
                        entry["interactive"] = True
                else:
                    gkey = ".".join(parts[: idx + 1])
                    gmeta = _group_metadata.get(gkey, {})
                    entry["description"] = gmeta.get("description", "")
                    if gmeta.get("default_action"):
                        entry["default_action"] = gmeta["default_action"]
                    entry["children"] = {}
                current[part] = entry
            current = current[part]

    # 2. Ensure all @group()-registered groups appear even if they have
    #    no leaf commands yet (edge case: empty group stubs)
    for gpath, gmeta in _group_metadata.items():
        parts = gpath.split(".")
        current = root
        for idx, part in enumerate(parts):
            is_last = idx == len(parts) - 1
            if part not in current:
                entry: dict[str, Any] = {"name": part}
                if not is_last:
                    entry["children"] = {}
                current[part] = entry
            if is_last:
                if gmeta.get("description") and not current[part].get("description"):
                    current[part]["description"] = gmeta["description"]
                if gmeta.get("default_action"):
                    current[part]["default_action"] = gmeta["default_action"]
                if "children" not in current[part]:
                    current[part]["children"] = {}
            current = current[part]

    # 3. Convert nested dict to sorted list-of-dicts
    def _to_list(node: dict) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": node["name"],
            "description": node.get("description", ""),
        }
        if "children" in node:
            result["children"] = sorted(
                [_to_list(v) for v in node["children"].values()],
                key=lambda x: x["name"],
            )
        if "default_action" in node:
            result["default_action"] = node["default_action"]
        if "params" in node:
            result["params"] = node["params"]
        if "flags" in node:
            result["flags"] = node["flags"]
        if node.get("interactive"):
            result["interactive"] = True
        return result

    tree = sorted(
        [_to_list(v) for v in root.values()],
        key=lambda x: x["name"],
    )
    _tree_cache = tree
    return tree


# ── Tree helpers (ported from tree.py) ────────────────────────────────────


def find_tree_node(path: list[str]) -> dict[str, Any] | None:
    """Walk the auto-generated tree to find a node by path."""
    nodes = get_command_tree()
    for token in path:
        found = None
        for node in nodes:
            if node["name"].lower() == token.lower():
                found = node
                break
        if found is None:
            return None
        nodes = found.get("children", [])
    return found


def find_command_depth(tokens: list[str]) -> int:
    """Walk the tree to find how many leading tokens form the command path."""
    tree = get_command_tree()
    current = tree
    for i, token in enumerate(tokens):
        found = None
        for node in current:
            if node["name"].lower() == token.lower():
                found = node
                break
        if found is None:
            return i
        children = found.get("children", [])
        if not children:
            return i + 1
        current = children
    return len(tokens)


def get_param_names(tokens: list[str]) -> list[str]:
    """Get the param names for a leaf command node."""
    tree = get_command_tree()
    current = tree
    node = None
    for token in tokens:
        found = None
        for n in current:
            if n["name"].lower() == token.lower():
                found = n
                break
        if found is None:
            return []
        node = found
        children = node.get("children", [])
        if not children:
            break
        current = children
    if node is None:
        return []
    return [p["name"] for p in node.get("params", [])]


# ── Interactive form resolution ──────────────────────────────────────────


def resolve_form_type(tokens: list[str]) -> str | None:
    """Return the interactive form type for a command path, or None.

    Tries progressively shorter paths (full path down to 2 tokens).
    """
    for i in range(len(tokens), 1, -1):
        key = ".".join(tokens[:i])
        if key in _interactive_forms:
            return _interactive_forms[key]
    return None


def register_interactive_form(path: str, form_type: str) -> None:
    """Register an interactive form mapping.

    Args:
        path: Dot-separated command path (e.g. ``"email.send"``).
        form_type: Frontend form type string (e.g. ``"email-send"``).
    """
    _interactive_forms[path] = form_type


# ── Command definitions for LLM ──────────────────────────────────────────


def get_definitions() -> list[dict]:
    """Return command definitions for LLM tool schema.

    Generated from the auto-generated command tree.
    """
    definitions: list[dict] = []

    def _walk(nodes: list[dict], prefix: list[str] | None = None) -> None:
        for node in nodes:
            path = (prefix or []) + [node["name"]]
            entry: dict = {"path": path, "canonical": f"!{' '.join(path)}"}
            desc = node.get("description")
            if desc:
                entry["description"] = desc
            flags = node.get("flags")
            if flags:
                entry["flags"] = [
                    {"name": f["name"], "type": f.get("type", "string"), "help": f.get("help", "")}
                    for f in flags
                ]
            params = node.get("params")
            if params:
                entry["params"] = [
                    {"name": p["name"], "required": p.get("required", False), "type": p.get("type", "string")}
                    for p in params
                ]
            definitions.append(entry)
            children = node.get("children")
            if children:
                _walk(children, path)

    _walk(get_command_tree())
    return definitions
