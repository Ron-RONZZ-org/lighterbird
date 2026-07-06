"""Command handlers for ``!email export eml`` and ``!email import eml``.

Registered paths:
    - email.export.eml
    - email.import.eml
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lighterbird.email.service import EmailService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service


@command("email.export.eml")
def email_export_eml(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email export eml <uuid>

    Export a message as .eml (RFC 822) attachment download.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing message UUID.",
            "Usage: !email export eml <uuid>",
        )
    uuid = remaining[0]
    svc: EmailService = get_email_service()
    eml_text = svc.export_eml(uuid)
    if eml_text is None:
        raise CommandValidationError(f"Message not found: {uuid[:8]}")
    return {
        "type": "status",
        "title": "Export .eml",
        "data": {
            "_summary": f"Exported message {uuid[:8]} as .eml",
            "uuid": uuid,
            "eml_size": len(eml_text),
        },
    }


@command("email.import.eml")
def email_import_eml(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email import eml <path>

    Import a .eml file as a new email draft.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing file path.",
            "Usage: !email import eml /path/to/file.eml",
        )
    path_str = remaining[0]
    # Path traversal protection: reject ".." components to prevent
    # directory escape. Absolute paths are allowed (users may import
    # from anywhere on their filesystem).
    raw = Path(path_str)
    if ".." in raw.parts:
        raise CommandValidationError(
            f"Path traversal not allowed: {path_str}",
            "Use a path without '..' components.",
        )
    resolved = raw.resolve()
    if not resolved.exists():
        raise CommandValidationError(f"File not found: {path_str}")
    if not resolved.is_file():
        raise CommandValidationError(f"Not a file: {path_str}")

    svc: EmailService = get_email_service()
    try:
        draft = svc.import_eml(str(resolved))
    except FileNotFoundError:
        raise CommandValidationError(f"File not found: {path_str}")
    except Exception as e:
        raise CommandValidationError(f"Import failed: {e}")
    return {
        "type": "status",
        "title": "Import .eml",
        "data": {
            "_summary": f"Imported {path_str} as draft {draft['uuid']}",
            "draft_uuid": draft["uuid"],
            "subject": draft["data"].get("subject", ""),
        },
    }
