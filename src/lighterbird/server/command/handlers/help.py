"""Command handler for ``!help``.

Shows available commands by listing the registry definitions.
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.registry import command, get_definitions


@command("help")
def show_help(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!help [command]"""
    defs = get_definitions()
    # Filter out aliases unless they're specifically requested
    show_aliases = flags.get("aliases", "").lower() in ("true", "1", "yes")
    if not show_aliases and remaining:
        # Filter to a specific command
        query = " ".join(remaining).lower()
        defs = [d for d in defs if query in " ".join(d.get("path", [])).lower()]

    lines = []
    for d in defs:
        if d.get("alias") and not show_aliases:
            continue
        canonical = d.get("canonical", "")
        lines.append({"name": canonical, "description": ""})

    return {
        "type": "help",
        "title": "Available Commands",
        "data": lines,
    }
