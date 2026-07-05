"""Command handler for ``!email send`` (extracted from email.py for size).

Registered paths:
    - email.send
"""

from __future__ import annotations

from typing import Any

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service
from lighterbird.email.service import EmailService


@command("email.send")
def email_send(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email send <to> <subject> [body] [--account <email>] [--cc email]
                    [--bcc email] [--priority N] [--body-format fmt]
                    [--file <name:base64>]

    Sends an email.  ``<to>`` and ``<subject>`` are required; ``<body>``
    is optional.  Use ``--cc`` / ``--bcc`` for additional recipients,
    ``--priority`` (1-5) to set importance, ``--body-format`` to choose
    markdown (default), html, or plain, and ``--file`` for attachments
    (repeatable, format: ``<filename>:<base64>``).
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing required args: <to> <subject> [body]",
            "Usage: !email send recipient@example.com \"Subject\" \"Body\" --account <email>",
        )
    to_str = remaining[0]
    subject = remaining[1]
    body = " ".join(remaining[2:]) if len(remaining) > 2 else ""
    account_email = flags.get("account", "")
    cc_str = flags.get("cc", "")
    bcc_str = flags.get("bcc", "")
    priority_str = flags.get("priority", "3")
    in_reply_to = flags.get("in-reply-to", "")
    body_format = flags.get("body-format", "markdown")
    file_flags = flags.get("file", "")
    cowrite_instr = flags.get("cowrite", "")
    cowrite_diff = "cowrite-diff" in flags

    svc: EmailService = get_email_service()

    # If no account specified, pick the first one
    if not account_email:
        accounts = svc.list_accounts()
        if not accounts:
            raise CommandValidationError("No email accounts configured.", "Add one with: !email account add")
        account_email = accounts[0]["email"]

    # Parse priority
    try:
        priority = int(priority_str)
        if priority < 1 or priority > 5:
            raise ValueError
    except ValueError:
        raise CommandValidationError(
            f"Invalid priority: {priority_str}. Must be 1 (highest) to 5 (lowest)."
        )

    # Validate body-format
    if body_format not in ("markdown", "html", "plain"):
        raise CommandValidationError(
            f"Invalid body-format: {body_format}. Choose markdown, html, or plain."
        )

    to_list = [t.strip() for t in to_str.split(",") if t.strip()]
    cc_list = [t.strip() for t in cc_str.split(",") if t.strip()] if cc_str else None
    bcc_list = [t.strip() for t in bcc_str.split(",") if t.strip()] if bcc_str else None

    # Parse --file flags: "name:base64,..." or multiple --file occurrences
    attachments = None
    if file_flags:
        attachments = []
        for item in file_flags.split(","):
            item = item.strip()
            if ":" in item:
                name, data = item.split(":", 1)
                attachments.append({"name": name, "data": data})
            else:
                attachments.append({"name": item, "data": ""})

    # ── LLM co-writing ─────────────────────────────────────────────────
    if cowrite_instr:
        import asyncio
        from lighterbird.server.cowrite.engine import cowrite as _cowrite_call

        fields = {"subject": subject, "body": body}
        try:
            result = asyncio.run(_cowrite_call(
                form_type="email-send",
                fields=fields,
                instruction=cowrite_instr,
            ))
            subject = result["revised"].get("subject", subject)
            body = result["revised"].get("body", body)
            if cowrite_diff:
                diff_lines = []
                for field, ops in result["edits"].items():
                    for op in ops:
                        if op["tag"] == "replace":
                            diff_lines.append(f"- {field}: {op['deleted']!r}")
                            diff_lines.append(f"+ {field}: {op['inserted']!r}")
                        elif op["tag"] == "delete":
                            diff_lines.append(f"- {field}: {op['deleted']!r}")
                        elif op["tag"] == "insert":
                            diff_lines.append(f"+ {field}: {op['inserted']!r}")
                if diff_lines:
                    body = body + f"\n\n-- Cowrite diff:\n" + "\n".join(diff_lines)
        except (RuntimeError, ValueError) as exc:
            raise CommandValidationError(f"Co-writing failed: {exc}")

    result = svc.send_email(account_email, to_list, subject, body,
                            cc=cc_list, bcc=bcc_list, priority=priority,
                            body_format=body_format,
                            attachments=attachments,
                            in_reply_to=in_reply_to or None)
    if result.get("status") == "queued":
        return {"type": "status", "title": "Queued for Delivery",
                "data": {"to": to_str, "subject": subject, "folder": "Outbox",
                         "error": result.get("error", "")}}
    return {"type": "status", "title": "Sent", "data": {"to": to_str, "subject": subject}}
