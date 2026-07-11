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

import base64
import json
from typing import Any

from lightercore.permissions import PermissionLevel

from lighterbird.email.service import EmailService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.handlers.email_eml import (  # noqa: F401
    email_export_eml,
    email_import_eml,
)

# Side-effect imports to register handlers split into sub-modules
from lighterbird.server.command.handlers.email_send import email_send  # noqa: F401
from lighterbird.core.storage import AttachmentStore
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
                "  !email signature add     — Add a named global signature\n"
                "  !email signature modify  — Modify a signature by UUID\n"
                "  !email signature delete  — Delete a signature by UUID\n"
                "  !email signature default — Show/set default signature\n"
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


@command("email.list", permission_level=PermissionLevel.READ)
def email_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email list [--limit N] [--folder NAME] [--not-folder NAME] [--all]
                  [--sort newest|oldest|sender] [--group conversation]
                  [--cursor TOKEN]

    By default excludes Trash, Spam, and Junk folders.
    Use ``--all`` to include all folders (including trash).
    Use ``--folder`` to filter to specific folder(s); comma-separated.
    Use ``--not-folder`` to exclude specific folder(s); comma-separated.
    Folder names use the ``{email}/{folder}`` convention, e.g.
    ``user@gmail.com/INBOX``.
    ``--sort`` controls display order: newest (default), oldest, sender.
    ``--group`` groups by conversation thread.
    ``--cursor`` provides a pagination token (returned as ``next_cursor``
    from a previous response) to fetch the next page.
    """
    svc: EmailService = get_email_service()
    limit = int(flags.get("limit", 20))
    folder_filter = flags.get("folder", "")
    not_folder_filter = flags.get("not-folder", "")
    include_all = "all" in flags
    sort_by = flags.get("sort", "newest")
    group_by = flags.get("group", "")
    cursor = flags.get("cursor", "")

    filters = _build_email_list_filters(flags, svc)
    if cursor:
        filters["cursor"] = cursor

    # Fetch limit+1 to detect whether there is a next page
    fetch_limit = limit + 1
    messages = [dict(m) for m in svc.search_messages(filters, limit=fetch_limit)]
    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]
        last = messages[-1]
        next_cursor = f"{last.get('received_at', '')}|{last.get('uuid', '')}"
    else:
        next_cursor = ""

    title_suffix = f" ({folder_filter})" if folder_filter else ""
    if not_folder_filter:
        title_suffix += f" (excl. {not_folder_filter})"

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
    if cursor:
        frontend_filters["cursor"] = cursor

    # Strip full body/html_body from list results; replace with 2000-char preview
    _PREVIEW_MAX = 2000
    for m in messages:
        full_body = m.get("body", "") or ""
        if full_body:
            preview = full_body[:_PREVIEW_MAX]
            if len(full_body) > _PREVIEW_MAX:
                preview += "\n\n[...]"
            m["body"] = preview
        if m.get("html_body"):
            m["html_body"] = ""

    return {
        "type": "email-list",
        "title": f"Email{title_suffix}",
        "data": {
            "messages": messages,
            "total": len(messages),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "filters": frontend_filters,
        },
    }


@command("email.read", permission_level=PermissionLevel.READ)
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


@command("email.reply", interactive=True, form_type="email-send")
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
    # Truncate quoted body to prevent context overflow from large emails
    _MAX_QUOTE_LINES = 100
    _MAX_QUOTE_CHARS = 10_000
    lines = body.split("\n")
    if len(lines) > _MAX_QUOTE_LINES or len(body) > _MAX_QUOTE_CHARS:
        truncated = lines[:_MAX_QUOTE_LINES]
        total_skipped = len(lines) - len(truncated)
        truncated.append(f"[...{total_skipped} more lines, {len(body) - sum(len(l) + 1 for l in truncated)} more chars...]")
        lines = truncated
    quoted = "\n".join(f"> {line}" for line in lines)

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


@command("email.forward", interactive=True, form_type="email-send")
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
    # Truncate forwarded body to prevent context overflow from large emails
    _MAX_FWD_LINES = 100
    _MAX_FWD_CHARS = 10_000
    lines = body.split("\n")
    if len(lines) > _MAX_FWD_LINES or len(body) > _MAX_FWD_CHARS:
        truncated = lines[:_MAX_FWD_LINES]
        total_skipped = len(lines) - len(truncated)
        truncated.append(f"[...{total_skipped} more lines, {len(body) - sum(len(l) + 1 for l in truncated)} more chars...]")
        lines = truncated
    truncated_body = "\n".join(lines)
    header = f"--- Forwarded message ---\nFrom: {msg.get('from_addr', '')}\nSubject: {msg.get('subject', '')}\nDate: {msg.get('received_at', '')}\n\n"
    forwarded = f"{header}{truncated_body}"

    initial_data: dict[str, Any] = {
        "subject": subject,
        "body": f"\n\n{forwarded}",
        "account": msg.get("account_email", ""),
    }

    # Include original attachments in the forward compose form
    store = AttachmentStore()
    attachment_rows = list(svc.db.execute(
        "SELECT filename, content_id FROM email_attachments WHERE message_uuid = ?",
        (uuid,),
    ))
    if attachment_rows:
        files = []
        for row in attachment_rows:
            try:
                raw = store.retrieve(uuid, row["content_id"])
                data_b64 = base64.b64encode(raw).decode("ascii")
                files.append({"name": row["filename"], "data": data_b64})
            except (FileNotFoundError, OSError):
                logger.warning("Missing attachment %s for message %s", row["content_id"][:12], uuid[:8])
                continue
        if files:
            initial_data["files"] = files

    return {
        "type": "form-required",
        "title": "Forward",
        "data": {
            "form": "email-send",
            "initialData": initial_data,
        },
    }


def _build_search_filters(flags: dict[str, str],
                          remaining: list[str]) -> tuple[dict[str, str], int, str]:
    """Build search filter dict and extract limit/query from flags."""
    filters: dict[str, str] = {}
    for key in ("from", "sender", "subject", "body", "to", "cc", "bcc",
                "participant", "priority", "after", "before"):
        if val := flags.get(key):
            filters[key] = val
    if "sender" in flags and "from" not in flags:
        filters["from"] = flags["sender"]
    limit = int(flags.get("limit", 50))
    query = " ".join(remaining) if remaining else ""
    if query:
        filters["query"] = query
    return filters, limit, query


@command("email.search", permission_level=PermissionLevel.READ,
         flags=[
             {"name": "from", "type": "string", "help": "Search by sender"},
             {"name": "sender", "type": "string", "help": "Search by sender (alias for --from)"},
             {"name": "subject", "type": "string", "help": "Search by subject (local headers)"},
             {"name": "to", "type": "string", "help": "Search by recipient (To field)"},
             {"name": "cc", "type": "string", "help": "Search by CC field"},
             {"name": "bcc", "type": "string", "help": "Search by BCC field (sent messages only)"},
             {"name": "participant", "type": "string", "help": "Search in From, To, and CC"},
             {"name": "priority", "type": "int", "help": "Filter by priority (1-10)"},
             {"name": "body", "type": "bool", "help": "Search message body via IMAP (slow, but finds text in header-only msgs)"},
             {"name": "header", "type": "bool", "help": "Search headers only (fast, local SQL)"},
             {"name": "after", "type": "string", "help": "Messages after date (YYYY-MM-DD)"},
             {"name": "before", "type": "string", "help": "Messages before date (YYYY-MM-DD)"},
             {"name": "limit", "type": "int", "help": "Max results (default 50)"},
             {"name": "account", "type": "string", "help": "Account email to search"},
             {"name": "folder", "type": "string", "help": "Folder name to search in"},
         ])
def email_search(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email search [query] [--from|--sender] [--subject] [--to] [--cc] [--bcc]
                   [--participant] [--priority N] [--body] [--header]
                   [--after DATE] [--before DATE] [--limit N]
                   [--account EMAIL] [--folder NAME]

    By default, a free-text query searches both headers and body via IMAP
    server-side SEARCH.  Use ``--header`` to restrict to local headers only
    (fast, no IMAP connection).  Use ``--body`` to force body search.

    Examples::

      !email search meeting                  # search headers + body via IMAP
      !email search --header meeting         # search headers only (local)
      !email search --body "project X"       # force body search via IMAP
      !email search --from alice             # local header search
      !email search --to bob --cc carol      # recipients
      !email search --participant dave       # anywhere in From/To/CC
      !email search --priority 1             # urgent only
    """
    svc: EmailService = get_email_service()
    filters, limit, query = _build_search_filters(flags, remaining)
    body_flag = "body" in flags
    header_flag = "header" in flags

    # Determine which search strategy to use
    needs_body = body_flag or (query and not header_flag)
    account_email = flags.get("account") or filters.get("account", "")

    if needs_body and account_email:
        # IMAP server-side SEARCH
        criteria = {}
        for key, imap_key in [("from", "from_"), ("sender", "from_"),
                              ("subject", "subject"), ("to", "to"),
                              ("cc", "cc"), ("participant", "participant")]:
            if val := flags.get(key):
                criteria[imap_key] = val
        if after_val := flags.get("after"):
            criteria["after"] = after_val
        if before_val := flags.get("before"):
            criteria["before"] = before_val
        messages = [dict(m) for m in svc.search_remote(
            account_email, query,
            folder=flags.get("folder"),
            criteria=criteria,
        )]
        messages = messages[:limit]
    elif filters:
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


@command("email.delete",
          flags=[
              {"name": "hard", "type": "bool",
               "help": "Permanently delete from IMAP server and local DB"},
          ])
def email_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email delete <uuid> [--hard]

    Default (soft): move to Trash folder on IMAP server.
    With ``--hard``: permanently remove from IMAP server and local DB.
    """
    if not remaining:
        raise CommandValidationError(
            "Missing message UUID.",
            "Usage: !email delete <uuid> [--hard]",
        )
    svc: EmailService = get_email_service()
    uuid = remaining[0]
    if "hard" in flags:
        svc.msg_ops.hard_delete_message(uuid)
        return {"type": "status", "title": "Permanently Deleted", "data": {"uuid": uuid[:8]}}
    svc.trash_message(uuid)
    return {"type": "status", "title": "Trashed", "data": {"uuid": uuid[:8]}}


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


@command("email.trash.list",
          permission_level=PermissionLevel.READ)
def email_trash_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email trash list

    Show messages in Trash folders.  Reuses the email list pane with
    only Trash folders selected.  No soft-delete on selection (messages
    are already in trash); only ``Ctrl+Delete`` / ``--hard`` for
    permanent deletion.
    """
    # Delegate to email_list with folder=Trash, adding a flag so the
    # frontend can identify this as a trash-only view.
    result = email_list(remaining, {"folder": "Trash", **flags})
    result["data"] = dict(result.get("data", {}))
    result["data"]["_isTrashView"] = True
    result["idKey"] = "email-trash-list"
    return result


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


@command("email.folders", permission_level=PermissionLevel.READ)
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

# ── Backward-compat aliases ────────────────────────────────────────
# The prefix-matching alias ``["email", "trash"] → ["email", "delete"]``
# would also capture ``["email", "trash", "list"]`` (rewriting it to
# ``email.delete list`` → dispatched as ``email_delete(["list"], {})``
# → erroneously returning "Trashed").  To avoid this, ``email.trash``
# is kept as a hidden command that delegates to ``email_delete``.
from lighterbird.server.command.registry import command

@command("email.trash", hidden=True,
          flags=[{"name": "hard", "type": "bool",
                   "help": "Permanently delete from IMAP server and local DB"}])
def email_trash(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """Deprecated.  Use ``!email delete`` instead."""
    return email_delete(remaining, flags)
