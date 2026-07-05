"""Command handlers for the ``!tag`` domain.

Unified cross-domain tag management.

Registered paths:
    - tag.list
    - tag.create
    - tag.rename
    - tag.delete
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_tag_service


@command("tag")
def tag_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!tag — Show available tag subcommands."""
    return {
        "type": "status",
        "title": "Tag Commands",
        "data": {
            "_summary": (
                "Available !tag commands:\n"
                "  !tag list                    — List all tags\n"
                "  !tag create <name>           — Create a tag\n"
                "  !tag rename <old> <new>      — Rename a tag\n"
                "  !tag delete <name>           — Delete a tag\n"
                "\nTags are shared across todo, journal, and all other domains.\n"
                "Use --color with create to set a hex color (e.g. --color #ff4444)."
            ),
        },
    }


@command("tag.list")
def tag_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!tag list [--domain NAME]

    Lists all tags, optionally filtered by domain usage.
    """
    svc = get_tag_service()
    domain = flags.get("domain")
    if domain:
        tags = svc.list_tags_for_domain(domain)
    else:
        tags = svc.list_tags()
    return {"type": "status", "title": "Tags", "data": {"tags": tags, "count": len(tags)}}


@command("tag.create")
def tag_create(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!tag create <name> [--color COLOR]

    Creates a new tag. Color is optional (hex, e.g. #ff4444).
    """
    if not remaining:
        raise CommandValidationError(
            "Missing tag name.",
            "Usage: !tag create <name> [--color #ff4444]",
        )
    name = remaining[0]
    color = flags.get("color", "")
    svc = get_tag_service()
    try:
        tag = svc.create_tag(name, color=color)
    except ValueError as e:
        raise CommandValidationError(str(e))
    return {"type": "status", "title": "Tag Created", "data": {"name": tag["name"], "color": tag["color"]}}


@command("tag.rename")
def tag_rename(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!tag rename <old-name> <new-name>

    Renames a tag. All items tagged with the old name are updated.
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing old or new tag name.",
            "Usage: !tag rename <old-name> <new-name>",
        )
    old_name = remaining[0]
    new_name = remaining[1]
    svc = get_tag_service()
    try:
        tag = svc.rename_tag(old_name, new_name)
    except ValueError as e:
        raise CommandValidationError(str(e))
    return {"type": "status", "title": "Tag Renamed", "data": {"old": old_name, "new": tag["name"]}}


@command("tag.delete")
def tag_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!tag delete <name> — Delete a tag and all its associations."""
    if not remaining:
        raise CommandValidationError(
            "Missing tag name.",
            "Usage: !tag delete <name>",
        )
    name = remaining[0]
    svc = get_tag_service()
    try:
        svc.delete_tag(name)
    except ValueError as e:
        raise CommandValidationError(str(e))
    return {"type": "status", "title": "Tag Deleted", "data": {"name": name}}
