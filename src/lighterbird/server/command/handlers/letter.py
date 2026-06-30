"""Command handlers for the ``!letter`` domain.

Registered paths:
    - letter.list
    - letter.add
    - letter.send
    - letter.view
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_letter_service
from lighterbird.letter.services.letters import LetterService


def _normalize_letter(letter: dict[str, Any]) -> dict[str, Any]:
    return dict(letter)


@command("letter")
def letter_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    return {
        "type": "status",
        "title": "Letter Commands",
        "data": {
            "_summary": (
                "Available !letter commands:\n"
                "  !letter list              — List letters\n"
                "  !letter view <uuid>       — View a letter\n"
                "  !letter add <object>      — Add a received letter\n"
                "  !letter send <recipient>  — Send a letter"
            ),
        },
    }


@command("letter.list")
def letter_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter list [--direction sent|received|all] [--sort newest|oldest|sender]
                    [--group conversation] [--limit N]"""
    svc: LetterService = get_letter_service()
    direction = flags.get("direction", "all")
    sort_by = flags.get("sort", "newest")
    group_by = flags.get("group", "")
    limit = int(flags.get("limit", 20))

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


@command("letter.add")
def letter_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter add <object> [--body <file-path>] [--sender SENDER]
                              [--recipient RECIPIENT] [--respond-to UUID]"""
    if not remaining:
        raise CommandValidationError(
            "Missing letter object/subject.",
            "Usage: !letter add \"Object\" [--body <path>] [--sender SENDER] [--recipient RECIPIENT]",
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
        if not parent:
            raise CommandValidationError(f"Letter not found: {respond_to[:8]}")
        data["respond_to_uuid"] = parent["uuid"]

    letter = svc.create(data)

    body_file = flags.get("body", "")
    if body_file:
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


@command("letter.send")
def letter_send(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter send <recipient> [--object OBJECT] [--body <file-path>]
                                  [--sender-profile UUID] [--recipient-contact UUID]
                                  [--respond-to UUID]"""
    if not remaining:
        raise CommandValidationError(
            "Missing recipient.",
            "Usage: !letter send \"Recipient Name\" [--object OBJECT] [--body <path>]",
        )
    recipient = remaining[0]
    svc: LetterService = get_letter_service()

    data: dict[str, Any] = {
        "direction": "sent",
        "object": flags.get("object", ""),
        "recipient_manual": recipient,
    }

    sender_profile = flags.get("sender-profile", "")
    if sender_profile:
        try:
            from lighterbird.server.deps import get_profiles_service
            profile_svc = get_profiles_service()
            profile = profile_svc.get(sender_profile)
            if profile:
                data["sender_profile"] = profile["uuid"]
                if not data.get("sender_manual"):
                    data["sender_manual"] = profile.get("full_name", "")
        except Exception:
            pass

    recipient_contact = flags.get("recipient-contact", "")
    if recipient_contact:
        try:
            from lighterbird.server.deps import get_contact_service
            contact_svc = get_contact_service()
            contact = contact_svc.get(recipient_contact)
            if contact:
                data["recipient_contact"] = contact["uuid"]
        except Exception:
            pass

    respond_to = flags.get("respond-to", "")
    if respond_to:
        parent = svc.get(respond_to)
        if not parent:
            raise CommandValidationError(f"Letter not found: {respond_to[:8]}")
        data["respond_to_uuid"] = parent["uuid"]

    letter = svc.create(data)

    body_file = flags.get("body", "")
    html_body = ""
    if body_file:
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
            html_body = svc.convert_to_html(content, fmt)
            svc.store_body(letter["uuid"], html_body)
        except CommandValidationError:
            raise
        except Exception as e:
            raise CommandValidationError(f"Failed to read body file: {e}")
    else:
        # Generate a minimal letter HTML
        html_body = _generate_letter_html(
            letter["uuid"],
            data.get("sender_manual", "") or data.get("sender_profile", ""),
            recipient,
            flags.get("object", ""),
        )
        svc.store_body(letter["uuid"], html_body)

    return {
        "type": "status",
        "title": "Letter Sent",
        "data": {
            "uuid": letter["uuid"],
            "object": flags.get("object", ""),
            "recipient": recipient,
            "html_body": html_body,
        },
    }


def _generate_letter_html(uuid: str, sender: str, recipient: str, subject: str) -> str:
    """Generate a nicely formatted HTML letter."""
    from datetime import date
    today = date.today().isoformat()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Letter — {subject}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Times New Roman", Georgia, serif;
      background: #fff; color: #000;
      padding: 2.5cm 2cm; line-height: 1.6; font-size: 12pt;
      max-width: 21cm; margin: 0 auto;
    }}
    .letterhead {{ text-align: right; margin-bottom: 2cm; }}
    .letterhead .sender {{ font-size: 11pt; color: #444; }}
    .letterhead .date {{ font-size: 11pt; color: #666; margin-top: 0.3cm; }}
    .recipient {{ margin-bottom: 1.5cm; }}
    .recipient .name {{ font-weight: bold; }}
    .subject {{ font-weight: bold; margin-bottom: 1cm; font-size: 13pt; }}
    .body {{ text-align: justify; }}
    .signature {{ margin-top: 2cm; }}
  </style>
</head>
<body>
  <div class="letterhead">
    <div class="sender">{sender}</div>
    <div class="date">{today}</div>
  </div>
  <div class="recipient">
    <div class="name">{recipient}</div>
  </div>
  <div class="subject">Re: {subject}</div>
  <div class="body">
    <p>[Letter content]</p>
  </div>
</body>
</html>"""


@command("letter.view")
def letter_view(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!letter view <uuid>"""
    if not remaining:
        raise CommandValidationError("Missing letter UUID.", "Usage: !letter view <uuid>")
    uuid = remaining[0]
    svc: LetterService = get_letter_service()
    letter_data = svc.get_with_thread(uuid)
    if not letter_data:
        raise CommandValidationError(f"Letter not found: {uuid[:8]}")
    body = svc.get_body(uuid)
    return {
        "type": "letter-view",
        "title": letter_data.get("object", "(untitled)"),
        "data": {
            "letter": _normalize_letter(letter_data),
            "body": body,
        },
    }
