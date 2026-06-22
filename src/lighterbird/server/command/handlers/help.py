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
    if remaining:
        query = " ".join(remaining).lower()
        defs = [d for d in defs if query in " ".join(d.get("path", [])).lower()]

    lines = [{"name": d.get("canonical", ""), "description": ""} for d in defs]
    return {
        "type": "help",
        "title": "Available Commands",
        "data": lines,
    }
