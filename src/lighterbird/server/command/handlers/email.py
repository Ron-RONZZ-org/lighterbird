"""Command handlers for the ``!email`` domain.

Registered paths:
    - email.list              (generic list with --folder/--sort/--cursor)
    - email.list.inbox        (view subcommand — presets folder=Inbox)
    - email.list.all          (view subcommand — no folder filter)
    - email.list.draft        (view subcommand — presets folder=Drafts)
    - email.list.trash        (view subcommand — presets folder=Trash)
    - email.list.outbox       (view subcommand — presets folder=Outbox)
    - email.list.archive      (view subcommand — presets folder=Archive)
    - email.list.junk         (view subcommand — presets folder=Junk)
    - email.list.spam         (view subcommand — presets folder=Spam)
    - email.send
    - email.search
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

from collections.abc import Callable
from typing import Any

from lightercore.permissions import PermissionLevel

from lighterbird.email.service import EmailService
from lighterbird.email.services.messages import _extract_match_snippet
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.handlers.email_eml import (  # noqa: F401
    email_export_eml,
    email_import_eml,
)

# Side-effect imports to register handlers split into sub-modules
from lighterbird.server.command.handlers.email_send import (  # noqa: F401
    email_send,
    email_draft_new,
)
from lighterbird.server.command.handlers.email_folder import (  # noqa: F401
    email_folder_root,
    email_folder_list,
    email_folder_add,
    email_folder_rename,
    email_folder_move,
    email_folder_delete,
)
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
                "  !email list                    — List messages (generic)\n"
                "  !email list inbox              — View inbox\n"
                "  !email list all                — View all (non-trash) folders\n"
                "  !email list draft              — View drafts\n"
                "  !email list trash              — View trash\n"
                "  !email list outbox             — View outbox\n"
                "  !email list archive            — View archive\n"
                "  !email list junk               — View junk\n"
                "  !email list spam               — View spam\n"
                "  !email send                    — Send an email\n"
                "  !email search                  — Search messages\n"
                "  !email draft new               — Compose a new draft\n"
                "  !email draft list              — List saved drafts\n"
                "  !email folder list             — List IMAP folders\n"
                "  !email account list            — List email accounts\n"
                "  !email account add             — Add an email account\n"
                "  !email account modify          — Modify an email account\n"
                "  !email account delete          — Delete an email account\n"
                "  !email signature list          — List account signatures\n"
                "  !email signature add           — Add a named global signature\n"
                "  !email signature modify        — Modify a signature by UUID\n"
                "  !email signature delete        — Delete a signature by UUID\n"
                "  !email signature default       — Show/set default signature\n"
                "  !email sieve list              — List Sieve scripts\n"
                "  !email sieve add               — Add a Sieve script\n"
                "  !email sieve modify            — Modify a Sieve script\n"
                "  !email sieve delete            — Delete a Sieve script\n"
                "  !email sieve activate          — Activate on an account\n"
                "  !email sieve deactivate        — Deactivate on an account\n"
                "  !email export eml <uuid>       — Export message as .eml file\n"
                "  !email import eml <path>       — Import .eml file as draft"
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


# ── View subcommand factory ────────────────────────────────────────────────


def _build_view_handler(folder: str | None = None, **response_flags: Any) -> Callable:
    """Factory for ``!email list <view>`` subcommand handlers.

    Each generated handler delegates to :func:`email_list` with the
    *folder* preset as a flag, and optionally merges extra response
    flags (e.g. ``_isTrashView``, ``_isDraftView``) into the result
    data so the frontend can identify the view type.

    Args:
        folder: IMAP folder name to filter by, or ``None`` for no filter.
        **response_flags: Extra keys injected into ``result["data"]``.

    Returns:
        A handler function compatible with ``@command()``.
    """
    def handler(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
        effective = dict(flags)
        if folder is not None:
            effective["folder"] = folder
        result = email_list(remaining, effective)
        if response_flags:
            result["data"] = {**result.get("data", {}), **response_flags}
        return result

    return handler


_VIEW_SPECS: list[tuple[str, str | None, dict[str, Any]]] = [
    ("inbox",   "Inbox",   {}),
    ("all",     None,      {}),
    ("draft",   "Drafts",  {"_isDraftView": True, "idKey": "email-draft-list"}),
    ("trash",   "Trash",   {"_isTrashView": True, "idKey": "email-trash-list"}),
    ("outbox",  "Outbox",  {"_isOutboxView": True}),
    ("archive", "Archive", {}),
    ("junk",    "Junk",    {}),
    ("spam",    "Spam",    {}),
]

for _name, _folder, _extra in _VIEW_SPECS:
    _fn = _build_view_handler(_folder, **_extra)
    _fn.__name__ = f"email_list_{_name}"
    command(f"email.list.{_name}")(_fn)


# ── Draft list alias ──────────────────────────────────────────────────────


@command("email.draft.list", permission_level=PermissionLevel.READ)
def email_draft_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email draft list

    Show messages in the Drafts folder.  Delegates to :func:`email_list`
    with folder preset — same as ``!email list draft`` but under the
    ``!email draft`` group.
    """
    return _build_view_handler("Drafts", _isDraftView=True, idKey="email-draft-list")(remaining, flags)


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

    **Enhanced local search** (``--header`` or named flags): a free-text query
    searches **all** message fields — subject, sender (from), recipients (to,
    cc), and body — with **relevance-ranked ordering**.  Results matching
    higher-signal fields (subject > sender > recipients > body) appear first.
    Each result includes a ``matched_in`` list showing which fields matched
    (frontend displays match badges).

    The ``--participant`` flag searches across From, To, and CC fields
    (previously only worked via IMAP remote search; now works locally too).

    When a query is present, the body field in list results is replaced with
    a **match-centered snippet** (instead of a simple prefix) so body matches
    at any position are visible.

    Examples::

      !email search meeting                  # search all fields (IMAP)
      !email search --header meeting         # search all fields locally (fast)
      !email search --header --from alice    # filter by sender + free-text
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

    # Apply body preview for list display
    _PREVIEW_MAX = 2000
    if query:
        # Match-centered snippet when query is present
        for m in messages:
            full_body = m.get("body", "") or ""
            if full_body:
                m["body"] = _extract_match_snippet(full_body, query)
            if m.get("html_body"):
                m["html_body"] = ""
    else:
        # Standard first-N-char preview for non-search listing
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
        "title": "Search Results",
        "data": {
            "messages": messages,
            "total": len(messages),
            "filters": frontend_filters,
            "query": query,
        },
    }



# (Account sub-commands moved to email_account.py)
# (Send moved to email_send.py)
# (EML export/import moved to email_eml.py)


