"""Command handlers for the ``!email`` domain.

Registered paths:
    - email.list
    - email.read
    - email.send
    - email.reply
    - email.forward
    - email.search
    - email.trash
    - email.archive
    - email.account.add
    - email.account.list
    - email.account.modify
    - email.account.delete
    - email.signature.add
    - email.signature.list
    - email.signature.modify
    - email.signature.delete
"""

from __future__ import annotations

import json
from typing import Any

from lighterbird.email.service import EmailService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.handlers.email_eml import (  # noqa: F401
    email_export_eml,
    email_import_eml,
)

# Side-effect imports to register handlers split into sub-modules
from lighterbird.server.command.handlers.email_send import email_send  # noqa: F401
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service

# ── Handlers ────────────────────────────────────────────────────────────


@command("email")
def email_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email — Show available email subcommands."""
    return {
        "type": "status",
        "title": "Email Commands",
        "data": {
            "_summary": (
                "Available !email commands:\n"
                "  !email list              — List inbox messages\n"
                "  !email read <uuid>       — Read a message\n"
                "  !email send              — Send an email\n"
                "  !email reply <uuid>      — Reply to a message\n"
                "  !email reply-all <uuid>  — Reply-all to a message\n"
                "  !email forward <uuid>    — Forward a message\n"
                "  !email search            — Search messages\n"
                "  !email trash <uuid>      — Trash a message\n"
                "  !email archive <uuid>    — Archive a message\n"
                "  !email move <uuid> --folder NAME  — Move to specific folder\n"
                "  !email folders           — List IMAP folders\n"
                "  !email account list      — List email accounts\n"
                "  !email account add       — Add an email account\n"
                "  !email account modify    — Modify an email account\n"
                "  !email account delete    — Delete an email account\n"
                "  !email signature list    — List account signatures\n"
                "  !email signature add     — Set a signature for an account\n"
                "  !email signature modify  — Modify an account signature\n"
                "  !email signature delete  — Delete an account signature\n"
                "  !email sieve list        — List Sieve scripts\n"
                "  !email sieve add         — Add a Sieve script\n"
                "  !email sieve modify      — Modify a Sieve script\n"
                "  !email sieve delete      — Delete a Sieve script\n"
                "  !email sieve activate    — Activate on an account\n"
                "  !email sieve deactivate  — Deactivate on an account\n"
                "  !email draft             — List / recall email drafts\n"
                "  !email export eml <uuid> — Export message as .eml file\n"
                "  !email import eml <path> — Import .eml file as draft"
            ),
        },
    }


def _build_email_list_filters(flags: dict[str, str], svc: EmailService) -> dict[str, Any]:
    """Build search filter dict from CLI flags for ``!email list``.

    Handles ``--folder``, ``--not-folder``, ``--all``, ``--sort``,
    and ``--group`` flags.  By default excludes Trash, Spam, Junk,
    and Bin folders.

    Args:
        flags: Parsed CLI flags.
        svc: Email service instance for account lookup.

    Returns:
        Filter dict suitable for ``EmailService.search_messages()``.
    """
    include_all = "all" in flags
    folder_filter = flags.get("folder", "")
    not_folder_filter = flags.get("not-folder", "")
    sort_by = flags.get("sort", "newest")
    group_by = flags.get("group", "")

    filters: dict[str, Any] = {}
    if folder_filter:
        folder_names = [f.strip() for f in folder_filter.split(",") if f.strip()]
        resolved_account: str | None = None

        for folder_name in folder_names:
            parts = folder_name.split("/", 1)
            if len(parts) == 2:
                acct_email, fname = parts
                accounts = svc.list_accounts()
                for acct in accounts:
                    if acct.get("email", "").lower() == acct_email.lower():
                        if resolved_account is None:
                            resolved_account = acct["email"]
                        filters["folder"] = [fname]
                        break
                else:
                    filters.setdefault("folder", []).append(folder_name)
            else:
                filters.setdefault("folder", []).append(folder_name)

        if resolved_account:
            filters["account"] = resolved_account

    if not_folder_filter:
        exclude_names = [f.strip() for f in not_folder_filter.split(",") if f.strip()]
        filters["exclude_folder"] = exclude_names

    if not folder_filter and not include_all:
        existing_exclude = filters.get("exclude_folder", [])
        filters["exclude_folder"] = [*existing_exclude, "Trash", "Spam", "Junk", "Bin"]

    if sort_by:
        filters["sort"] = sort_by
    if group_by:
        filters["group"] = group_by

    return filters


@command("email.list")
def email_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email list [--limit N] [--folder NAME] [--not-folder NAME] [--all]
                  [--sort newest|oldest|sender] [--group conversation]

    By default excludes Trash, Spam, and Junk folders.
    Use ``--all`` to include all folders (including trash).
    Use ``--folder`` to filter to specific folder(s); comma-separated.
    Use ``--not-folder`` to exclude specific folder(s); comma-separated.
    Folder names use the ``{email}/{folder}`` convention, e.g.
    ``user@gmail.com/INBOX``.
    ``--sort`` controls display order: newest (default), oldest, sender.
    ``--group`` groups by conversation thread.
    """
    svc: EmailService = get_email_service()
    limit = int(flags.get("limit", 20))
    folder_filter = flags.get("folder", "")
    not_folder_filter = flags.get("not-folder", "")
    include_all = "all" in flags
    sort_by = flags.get("sort", "newest")
    group_by = flags.get("group", "")

    filters = _build_email_list_filters(flags, svc)

    messages = [dict(m) for m in svc.search_messages(filters, limit=limit)]
    title_suffix = f" ({folder_filter})" if folder_filter else ""
    if not_folder_filter:
        title_suffix += f" (excl. {not_folder_filter})"
    if not folder_filter and not include_all:
        title_suffix = "" if title_suffix else " (no trash)"

    frontend_filters = {}
    if "account" in filters:
        frontend_filters["account_email"] = filters["account"]
    if "folder" in filters:
        fld = filters["folder"]
        frontend_filters["folder"] = fld[0] if isinstance(fld, list) else fld
    if sort_by:
        frontend_filters["sort"] = sort_by
    if group_by:
        frontend_filters["group"] = group_by

    return {
        "type": "email-list",
        "title": f"Inbox{title_suffix}",
        "data": {
            "messages": messages,
            "total": len(messages),
            "filters": frontend_filters,
        },
    }


@command("email.read")
def email_read(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email read <uuid>"""
    if not remaining:
        raise CommandValidationError("Missing message UUID.", "Usage: !email read <uuid>")
    uuid = remaining[0]
    svc: EmailService = get_email_service()
    msg = svc.get_message(uuid)
    if not msg:
        raise CommandValidationError(f"Message not found: {uuid[:8]}")
    return {"type": "email", "title": msg.get("subject", "(no subject)"), "data": dict(msg)}





@command("email.reply")
def email_reply(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email reply <uuid> [--all]

    Opens the compose form pre-populated as a reply to the given message.
    Use ``--all`` to Reply-All (include all original recipients).
    """
    if not remaining:
        raise CommandValidationError(
            "Missing message UUID.",
            "Usage: !email reply <uuid> [--all]",
        )
    uuid = remaining[0]
    svc: EmailService = get_email_service()
    msg = svc.get_message(uuid)
    if not msg:
        raise CommandValidationError(f"Message not found: {uuid[:8]}")

    reply_all = "all" in flags

    # Detect if message was sent by the user (e.g. in Sent folder).
    # If so, reply to original recipients instead of self.
    from_addr = (msg.get("from_addr") or "").lower()
    account_email = (msg.get("account_email") or "").lower()
    is_from_self = from_addr and account_email and account_email in from_addr

    orig_to = (json.loads(msg.get("to_recipients", "[]"))
               if isinstance(msg.get("to_recipients"), str)
               else (msg.get("to_recipients") or []))
    orig_cc = (json.loads(msg.get("cc_recipients", "[]"))
               if isinstance(msg.get("cc_recipients"), str)
               else (msg.get("cc_recipients") or []))

    if is_from_self:
        # Message sent by user — reply to original To recipients
        to = ", ".join(orig_to) if orig_to else ""
    else:
        to = msg.get("from_addr", "")

    cc = ""
    if reply_all:
        if is_from_self:
            # Reply-all to self — include CC recipients alongside To
            cc_list = [r.strip() for r in orig_cc if r.strip().lower() != account_email]
            cc = ", ".join(cc_list) if cc_list else ""
        else:
            # Reply-all from someone else — include To + CC (excluding self)
            to_list = [to]
            for r in orig_to:
                if r.strip().lower() != account_email:
                    to_list.append(r.strip())
            to = ", ".join(to_list)
            cc_list = [r.strip() for r in orig_cc if r.strip().lower() != account_email]
            cc = ", ".join(cc_list) if cc_list else ""

    subject = msg.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    body = msg.get("body", "") or ""
    quoted = "\n".join(f"> {line}" for line in body.split("\n"))

    initial_data: dict[str, Any] = {
        "to": to,
        "subject": subject,
        "body": f"\n\n{quoted}",
        "account": msg.get("account_email", ""),
    }
    if cc:
        initial_data["cc"] = cc

    return {
        "type": "form-required",
        "title": "Reply",
        "data": {
            "form": "email-send",
            "initialData": initial_data,
        },
    }


@command("email.forward")
def email_forward(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email forward <uuid>

    Opens the compose form pre-populated as a forward of the given message.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing message UUID.",
            "Usage: !email forward <uuid>",
        )
    uuid = remaining[0]
    svc: EmailService = get_email_service()
    msg = svc.get_message(uuid)
    if not msg:
        raise CommandValidationError(f"Message not found: {uuid[:8]}")

    subject = msg.get("subject", "")
    if not subject.lower().startswith("fwd:"):
        subject = f"Fwd: {subject}"

    body = msg.get("body", "") or ""
    header = f"--- Forwarded message ---\nFrom: {msg.get('from_addr', '')}\nSubject: {msg.get('subject', '')}\nDate: {msg.get('received_at', '')}\n\n"
    forwarded = f"{header}{body}"

    return {
        "type": "form-required",
        "title": "Forward",
        "data": {
            "form": "email-send",
            "initialData": {
                "subject": subject,
                "body": f"\n\n{forwarded}",
                "account": msg.get("account_email", ""),
            },
        },
    }


def _build_search_filters(flags: dict[str, str],
                          remaining: list[str]) -> tuple[dict[str, str], int, str]:
    """Build search filter dict and extract limit/query from flags."""
    filters: dict[str, str] = {}
    for key in ("from", "subject", "body", "after", "before"):
        if val := flags.get(key):
            filters[key] = val
    limit = int(flags.get("limit", 50))
    query = " ".join(remaining) if remaining else ""
    if query:
        filters["query"] = query
    return filters, limit, query


@command("email.search")
def email_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email search [--from] [--subject] [--body] [--after] [--before] [--limit]"""
    svc: EmailService = get_email_service()
    filters, limit, query = _build_search_filters(flags, remaining)

    if filters:
        messages = [dict(m) for m in svc.search_messages(filters, limit=limit)]
    else:
        messages = [dict(m) for m in svc.list_messages(limit=limit)]

    frontend_filters = {k: v for k, v in filters.items() if k != "query"}

    return {
        "type": "email-list",
        "title": "Search Results",
        "data": {
            "messages": messages,
            "total": len(messages),
            "filters": frontend_filters,
            "query": query,
        },
    }


@command("email.trash")
def email_trash(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email trash <uuid>"""
    if not remaining:
        raise CommandValidationError("Missing message UUID.", "Usage: !email trash <uuid>")
    svc: EmailService = get_email_service()
    svc.trash_message(remaining[0])
    return {"type": "status", "title": "Trashed", "data": {"uuid": remaining[0][:8]}}


@command("email.archive")
def email_archive(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email archive <uuid> [--folder NAME]

    Move a message to the Archive folder (default: "Archive").
    Use ``--folder`` to specify a different destination folder.
    """
    if not remaining:
        raise CommandValidationError("Missing message UUID.", "Usage: !email archive <uuid>")
    svc: EmailService = get_email_service()
    folder = flags.get("folder", "Archive")
    svc.move_message(remaining[0], folder)
    return {"type": "status", "title": "Archived", "data": {"uuid": remaining[0][:8], "folder": folder}}


@command("email.move")
def email_move(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email move <uuid> --folder NAME

    Move a message to a specific folder.
    Use ``!email folders`` to see available folders.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing message UUID.",
            "Usage: !email move <uuid> --folder NAME",
        )
    folder = flags.get("folder", "")
    if not folder:
        raise CommandValidationError(
            "Missing --folder flag.",
            "Usage: !email move <uuid> --folder NAME",
        )
    svc: EmailService = get_email_service()
    svc.move_message(remaining[0], folder)
    return {
        "type": "status",
        "title": "Moved",
        "data": {"uuid": remaining[0][:8], "folder": folder},
    }


@command("email.folders")
def email_folders(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email folders [--account email]

    List known IMAP folders from the database (populated during sync).
    Use ``--account`` to filter by account email.
    """
    svc: EmailService = get_email_service()
    account = flags.get("account", "")
    if account:
        folders = svc.messages.list_folders(account_email=account)
    else:
        folders = svc.messages.list_folders()
    return {
        "type": "status",
        "title": "Folders",
        "data": {"folders": folders, "count": len(folders)},
    }



# (Account sub-commands moved to email_account.py)
# (Send moved to email_send.py)
# (EML export/import moved to email_eml.py)
