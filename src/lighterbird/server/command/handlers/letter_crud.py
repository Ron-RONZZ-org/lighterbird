"""Command handlers for ``!letter`` CRUD operations.

Registered paths:
    - letter.list
    - letter.add
    - letter.view
"""

from __future__ import annotations

from typing import Any

from lightercore.permissions import PermissionLevel
from lighterbird.letter.services.letters import LetterService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.helpers import require_found, require_uuid
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_letter_service


def _normalize_letter(letter: dict[str, Any]) -> dict[str, Any]:
    return dict(letter)


@command("letter.list", permission_level=PermissionLevel.READ)
def letter_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter list [--direction sent|received|all] [--sort newest|oldest|sender]
                    [--group conversation] [--limit N] [--tag TAG,...]"""
    svc: LetterService = get_letter_service()
    direction = flags.get("direction", "all")
    sort_by = flags.get("sort", "newest")
    group_by = flags.get("group", "")
    limit = int(flags.get("limit", 20))

    # Parse tags (supports comma-separated: --tag a,b)
    tags = svc.normalize_tags([flags["tag"]]) if "tag" in flags else None

    order_by = "created_at"
    desc = True
    if sort_by == "oldest":
        desc = False
    elif sort_by == "sender":
        order_by = "sender_manual"
        desc = False

    if group_by == "conversation":
        letters = [_normalize_letter(l) for l in svc.list_grouped(limit=limit)]
    else:
        letters = [_normalize_letter(l) for l in svc.list(
            limit=limit, direction=direction, order_by=order_by, desc=desc,
            tags=tags,
        )]

    return {
        "type": "letter-list",
        "title": "Letters",
        "data": {
            "letters": letters,
            "total": len(letters),
            "filters": {"direction": direction, "sort": sort_by, "group": group_by},
        },
    }


@command("letter.add", interactive=True)
def letter_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter add <object> [--body <file-path>] [--body-text CONTENT] [--body-format FORMAT]
                              [--sender SENDER] [--recipient RECIPIENT] [--respond-to UUID]
                              [--tag TAG,...]"""
    if not remaining:
        raise CommandValidationError(
            "Missing letter object/subject.",
            "Usage: !letter add \"Object\" [--body <path>] [--sender SENDER] [--recipient RECIPIENT]"
            " [--tag TAG,...]",
        )
    subject = remaining[0]
    svc: LetterService = get_letter_service()

    data: dict[str, Any] = {
        "direction": "received",
        "object": subject,
        "sender_manual": flags.get("sender", ""),
        "recipient_manual": flags.get("recipient", ""),
    }

    respond_to = flags.get("respond-to", "")
    if respond_to:
        parent = svc.get(respond_to)
        require_found(parent, respond_to[:8], "letter")
        data["respond_to_uuid"] = parent["uuid"]

    letter = svc.create(data)

    # Set tags
    if "tag" in flags:
        tags = svc.normalize_tags([flags["tag"]])
        if tags:
            svc.set_tags(letter["uuid"], tags)

    body_file = flags.get("body", "")
    body_text = flags.get("body-text", "")
    if body_text:
        body_format = flags.get("body-format", "markdown")
        html = svc.convert_to_html(body_text, body_format)
        svc.store_body(letter["uuid"], html)
    elif body_file:
        try:
            from pathlib import Path
            body_path = Path(body_file)
            if not body_path.exists():
                raise CommandValidationError(f"Body file not found: {body_file}")
            content = body_path.read_text(encoding="utf-8")
            suffix = body_path.suffix.lower()
            fmt = "html"
            if suffix == ".md":
                fmt = "markdown"
            elif suffix == ".txt":
                fmt = "text"
            html = svc.convert_to_html(content, fmt)
            svc.store_body(letter["uuid"], html)
        except CommandValidationError:
            raise
        except Exception as e:
            raise CommandValidationError(f"Failed to read body file: {e}")

    return {
        "type": "status",
        "title": "Letter Added",
        "data": {"uuid": letter["uuid"], "object": subject, "direction": "received"},
    }


@command("letter.view", permission_level=PermissionLevel.READ)
def letter_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter view <uuid>"""
    uuid = require_uuid(remaining, "Usage: !letter view <uuid>")
    svc: LetterService = get_letter_service()
    letter_data = svc.get_with_thread(uuid)
    require_found(letter_data, uuid[:8], "letter")
    body = svc.get_body(uuid)
    return {
        "type": "letter-view",
        "title": letter_data.get("object", "(untitled)"),
        "data": {
            "letter": _normalize_letter(letter_data),
            "body": body,
        },
    }
