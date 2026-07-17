"""Command handlers for ``!email send`` and ``!email draft new``.

Registered paths:
    - email.send
    - email.draft.new
"""

from __future__ import annotations

from typing import Any

from lighterbird.email.service import EmailService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service


# ── Shared send core ──────────────────────────────────────────────────────


def _send_email_core(
    to_str: str,
    subject: str,
    body: str,
    flags: dict[str, str],
) -> dict[str, Any]:
    """Validate inputs and send an email via the service.

    Shared by ``!email send`` and ``!email draft new`` (when invoked
    with all required args).

    Args:
        to_str: Comma-separated recipient addresses.
        subject: Email subject line.
        body: Email body text.
        flags: Parsed CLI flags (account, cc, bcc, priority,
            body-format, signature options, file attachments, etc.).

    Returns:
        Response dict with type ``"status"``.

    Raises:
        CommandValidationError: On invalid inputs.
    """
    account_email = flags.get("account", "")
    cc_str = flags.get("cc", "")
    bcc_str = flags.get("bcc", "")
    priority_str = flags.get("priority", "3")
    in_reply_to = flags.get("in-reply-to", "")
    body_format = flags.get("body-format", "markdown")
    file_flags = flags.get("file", "")
    signature_override = flags.get("signature", None)
    signature_name = flags.get("signature-name", None)
    no_signature = "no-signature" in flags
    save_as_sample = flags.get("no-save-sample", "").lower() not in ("1", "true", "yes")
    svc: EmailService = get_email_service()

    # If no account specified, pick the first one
    if not account_email:
        accounts = svc.list_accounts()
        if not accounts:
            raise CommandValidationError(
                "No email accounts configured.",
                "Add one with: !email account add",
            )
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

    # Parse --file flag: JSON array of {name, data} objects
    attachments = None
    if file_flags:
        import json as _json

        try:
            parsed = _json.loads(file_flags)
            if isinstance(parsed, list):
                attachments = parsed
        except (_json.JSONDecodeError, TypeError):
            # Fallback: legacy comma-separated "name:base64,..." format
            attachments = []
            for item in file_flags.split(","):
                item = item.strip()
                if ":" in item:
                    name, data = item.split(":", 1)
                    attachments.append({"name": name, "data": data})
                else:
                    attachments.append({"name": item, "data": ""})

    # Resolve signature override
    signature_value: str | None = None
    signature_format: str = "plain"
    if no_signature:
        signature_value = ""  # empty string = send without signature
    elif signature_name is not None:
        sig = svc.signatures.resolve(account_email, name=signature_name)
        signature_value = (sig or {}).get("signature_text", "")
        signature_format = (sig or {}).get("signature_format", "plain")
    elif signature_override is not None:
        signature_value = signature_override
        signature_format = flags.get("signature-format", "plain")

    try:
        svc.send_email(
            account_email,
            to_list,
            subject,
            body,
            cc=cc_list,
            bcc=bcc_list,
            priority=priority,
            body_format=body_format,
            attachments=attachments,
            signature=signature_value,
            signature_format=signature_format,
            in_reply_to=in_reply_to or None,
            save_as_sample=save_as_sample,
        )
    except ValueError as e:
        raise CommandValidationError(
            str(e),
            suggestion="Check the account exists and has a password configured.",
        )

    # Trigger background SMTP delivery
    from lighterbird.server.tasks import enqueue_email_send

    enqueue_email_send()

    return {
        "type": "status",
        "title": "Queued for Delivery",
        "data": {"to": to_str, "subject": subject, "folder": "Outbox"},
    }


# ── email.send ────────────────────────────────────────────────────────────


@command(
    "email.send",
    interactive=True,
    params=[
        {
            "name": "to",
            "type": "string",
            "help": "Recipient email address(es), comma-separated",
            "required": True,
        },
        {
            "name": "subject",
            "type": "string",
            "help": "Email subject",
            "required": True,
        },
        {
            "name": "body",
            "type": "string",
            "help": "Email body text",
            "required": False,
        },
    ],
    flags=[
        {"name": "account", "type": "string", "help": "Sender account email"},
        {
            "name": "cc",
            "type": "string",
            "help": "CC recipients (comma-separated)",
        },
        {
            "name": "bcc",
            "type": "string",
            "help": "BCC recipients (comma-separated)",
        },
        {
            "name": "priority",
            "type": "string",
            "help": "Priority 1-5 (default 3)",
        },
        {
            "name": "body-format",
            "type": "string",
            "help": "Body format: markdown, html, or plain",
        },
        {
            "name": "signature",
            "type": "string",
            "help": "Override account signature text",
        },
        {
            "name": "signature-name",
            "type": "string",
            "help": "Use a named signature from the account",
        },
        {
            "name": "signature-format",
            "type": "string",
            "help": "Signature format when using --signature: plain, html, or markdown",
            "values": ["plain", "html", "markdown"],
        },
        {
            "name": "no-signature",
            "type": "bool",
            "help": "Send without any signature",
        },
        {
            "name": "file",
            "type": "string",
            "help": 'Attachment JSON array [{"name":...,"data":base64}] or legacy name:base64,...',
        },
        {
            "name": "no-save-sample",
            "type": "bool",
            "help": "Do not save as writing sample",
        },
    ],
)
def email_send(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email send <to> <subject> [body] [--account <email>] [--cc email]
                    [--bcc email] [--priority N] [--body-format fmt]
                    [--signature <text>] [--signature-name <name>]
                    [--no-signature]
                    [--file <name:base64>]

    Sends an email.  ``<to>`` and ``<subject>`` are required; ``<body>``
    is optional.  Uses ``_send_email_core`` for shared logic with
    ``!email draft new``.
    """
    if len(remaining) < 2:
        raise CommandValidationError(
            "Missing required args: <to> <subject> [body]",
            "Usage: !email send recipient@example.com \"Subject\" \"Body\" --account <email>",
        )
    return _send_email_core(
        remaining[0],
        remaining[1],
        " ".join(remaining[2:]) if len(remaining) > 2 else "",
        flags,
    )


# ── email.draft.new ───────────────────────────────────────────────────────


@command(
    "email.draft.new",
    interactive=True,
    form_type="email-send",
    params=[
        {
            "name": "to",
            "type": "string",
            "help": "Recipient email address(es), comma-separated",
            "required": False,
        },
        {
            "name": "subject",
            "type": "string",
            "help": "Email subject",
            "required": False,
        },
        {
            "name": "body",
            "type": "string",
            "help": "Email body text",
            "required": False,
        },
    ],
    flags=[
        {"name": "account", "type": "string", "help": "Sender account email"},
        {"name": "cc", "type": "string", "help": "CC recipients (comma-separated)"},
        {"name": "bcc", "type": "string", "help": "BCC recipients (comma-separated)"},
    ],
)
def email_draft_new(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email draft new [to] [subject] [body] [--account <email>] [--cc] [--bcc]

    Opens the compose form for drafting a new email.  Any provided
    positional args pre-populate the form fields.  The form auto-saves
    drafts as the user types (frontend handles the draft REST API).

    All params are optional — the command always opens the form so the
    user can compose freely.
    """
    initial_data: dict[str, Any] = {}
    if remaining:
        initial_data["to"] = remaining[0]
    if len(remaining) > 1:
        initial_data["subject"] = remaining[1]
    if len(remaining) > 2:
        initial_data["body"] = " ".join(remaining[2:])
    for key in ("account", "cc", "bcc"):
        if flags.get(key):
            initial_data[key] = flags[key]

    return {
        "type": "form-required",
        "title": "New Draft",
        "data": {
            "form": "email-send",
            "initialData": initial_data,
        },
    }
