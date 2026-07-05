"""Command handlers for ``!letter`` export and import.

Registered paths:
    - letter.export
    - letter.export.md
    - letter.import
    - letter.import.md
"""

from __future__ import annotations

from typing import Any

from lighterbird.letter.services.letters import LetterService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_letter_service


@command("letter.export")
def letter_export(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "status",
        "title": "Letter Export Commands",
        "data": {
            "_summary": (
                "Available !letter export commands:\n"
                "  !letter export md <uuid>   — Export as markdown\n"
            ),
        },
    }


@command("letter.export.md")
def letter_export_md(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter export md <uuid>"""
    if not remaining:
        raise CommandValidationError(
            "Missing letter UUID.",
            "Usage: !letter export md <uuid>",
        )
    uuid = remaining[0]
    svc: LetterService = get_letter_service()
    letter = svc.get(uuid)
    if not letter:
        raise CommandValidationError(f"Letter not found: {uuid[:8]}")
    md = svc.export_md(uuid=uuid)
    from lighterbird.core.paths import data_dir
    export_dir = data_dir() / "letters" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    out_path = export_dir / f"{uuid[:8]}.md"
    out_path.write_text(md, encoding="utf-8")
    return {
        "type": "status",
        "title": "Letter Exported",
        "data": {
            "uuid": uuid,
            "output": str(out_path),
        },
    }


@command("letter.import")
def letter_import_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "status",
        "title": "Letter Import Commands",
        "data": {
            "_summary": (
                "Available !letter import commands:\n"
                "  !letter import md <path>   — Import from markdown file\n"
            ),
        },
    }


@command("letter.import.md")
def letter_import_md(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter import md <path>"""
    if not remaining:
        raise CommandValidationError(
            "Missing file path.",
            "Usage: !letter import md <path>",
        )
    path = remaining[0]
    svc: LetterService = get_letter_service()
    try:
        uuids = svc.import_md(path)
    except FileNotFoundError as e:
        raise CommandValidationError(str(e))
    except Exception as e:
        raise CommandValidationError(f"Import failed: {e}")
    return {
        "type": "status",
        "title": "Letter Imported",
        "data": {
            "uuids": uuids,
            "count": len(uuids),
        },
    }
