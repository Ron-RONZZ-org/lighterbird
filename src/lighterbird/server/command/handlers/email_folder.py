"""Command handlers for ``!email folder`` subcommands.

Registered paths:
    - email.folder.list
    - email.folder.add
    - email.folder.rename
    - email.folder.move
    - email.folder.delete
"""

from __future__ import annotations

import logging
from typing import Any

from lightercore.permissions import PermissionLevel

from lighterbird.email.service import EmailService
from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.registry import command
from lighterbird.server.deps import get_email_service

logger = logging.getLogger(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────


def _parse_folder_path(path: str) -> tuple[str, str]:
    """Parse a ``{account_email}/{folder}`` path into ``(account_email, folder_name)``.

    Args:
        path: Folder path in the form ``user@example.com/INBOX/MyFolder``.

    Returns:
        Tuple of ``(account_email, folder_name)``.

    Raises:
        CommandValidationError: If the path does not contain at least one ``/``.
    """
    parts = path.split("/", 1)
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise CommandValidationError(
            f"Invalid folder path: '{path}'. "
            "Expected format: {account_email}/{folder_name} "
            "(e.g. user@gmail.com/INBOX).",
        )
    return parts[0], parts[1]


def _resolve_parent(
    parent_arg: str,
) -> tuple[str, str | None]:
    """Resolve the ``--parent`` flag into ``(account_email, parent_folder)``.

    When ``--parent`` is just an email address, the folder is created at
    root level of that account (``parent_folder`` is ``None``).
    When it contains a ``/``, it is ``{account}/{parent_path}``.

    Args:
        parent_arg: The ``--parent`` flag value.

    Returns:
        Tuple of ``(account_email, parent_folder_or_None)``.
    """
    if "/" in parent_arg:
        acct_email, parent_fld = parent_arg.split("/", 1)
        return acct_email, parent_fld
    return parent_arg, None


def _build_folder_name(
    folder_name: str,
    parent: str | None,
) -> str:
    """Build the full IMAP folder name from a simple name and optional parent.

    When *parent* is given, the full name is ``{parent}/{folder_name}``.
    Otherwise it's just ``{folder_name}``.

    Args:
        folder_name: The simple folder name (e.g. ``"MyFolder"``).
        parent: Optional parent path (e.g. ``"INBOX"``).

    Returns:
        The full IMAP folder path.
    """
    if parent:
        return f"{parent}/{folder_name}"
    return folder_name


def _connect_imap(
    account_email: str,
    svc: EmailService,
) -> tuple[dict, Any]:
    """Look up account and open an IMAP connection.

    Returns ``(account_dict, IMAPClient)`` or raises on failure.
    """
    from lighterbird.email.imap.client import IMAPClient

    acct = svc.accounts.get_account_with_password(account_email)
    if not acct:
        raise CommandValidationError(f"Account not found: {account_email}")
    if not acct.get("password"):
        raise CommandValidationError(
            f"No password configured for {account_email}. "
            f"Set it with: !email account modify {account_email} --password <pw>",
        )

    client = IMAPClient(
        host=acct.get("imap_server", ""),
        port=acct.get("imap_port", 993),
        use_ssl=acct.get("imap_use_ssl", 1) == 1,
    )
    try:
        client.connect(
            username=acct.get("imap_username", "") or account_email,
            password=acct["password"],
        )
    except Exception as e:
        raise CommandValidationError(f"IMAP connection failed for {account_email}: {e}")

    return acct, client


# ── Handlers ────────────────────────────────────────────────────────────────


@command("email.folder")
def email_folder_root(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email folder — Show available folder subcommands."""
    return {
        "type": "status",
        "title": "Email Folder Commands",
        "data": {
            "_summary": (
                "Available !email folder commands:\n"
                "  !email folder list                  — Show folder tree\n"
                "  !email folder add <name> --parent P  — Create a folder\n"
                "  !email folder rename <path> <name>   — Rename a folder\n"
                "  !email folder move <path> --parent P  — Move folder to parent\n"
                "  !email folder delete <path>           — Delete a folder\n\n"
                "Folder paths use the format: {account_email}/{folder_name}\n"
                "  e.g. user@gmail.com/INBOX/MyFolder\n\n"
                "The --parent flag takes {account_email} for root level, or\n"
                "  {account_email}/{folder} for a subfolder parent."
            ),
        },
    }


@command("email.folder.list", permission_level=PermissionLevel.READ)
def email_folder_list(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email folder list [--account EMAIL]

    Show all IMAP folders as a hierarchical tree.  Use ``--account`` to
    filter by account email.
    """
    svc: EmailService = get_email_service()
    account = flags.get("account", "")
    if account:
        rows = list(svc.db.execute(
            "SELECT account_email, name, special_use, created_at, updated_at "
            "FROM folders WHERE account_email = ? ORDER BY name",
            (account,),
        ))
    else:
        rows = list(svc.db.execute(
            "SELECT account_email, name, special_use, created_at, updated_at "
            "FROM folders ORDER BY account_email, name",
        ))

    folders = []
    for row in rows:
        folders.append({
            "account_email": row["account_email"],
            "folder_name": row["name"],
            "special_use": row["special_use"],
            "label": f"{row['account_email']}/{row['name']}",
        })

    all_folders = list(svc.db.execute("SELECT DISTINCT account_email FROM folders ORDER BY account_email"))

    return {
        "type": "folder-list",
        "title": "Folders",
        "data": {
            "folders": folders,
            "total": len(folders),
            "accounts": [r["account_email"] for r in all_folders],
        },
    }


@command("email.folder.add", interactive=True, form_type="email-folder-add",
          params=[
              {"name": "name", "type": "string", "required": True,
               "help": "Folder name to create"},
          ],
          flags=[
              {"name": "parent", "type": "string", "required": False,
               "help": "Parent path: {account_email} or {account_email}/{folder}"},
          ])
def email_folder_add(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email folder add <name> [--parent {account_email}] [--parent {account_email}/{folder}]

    Create a new IMAP folder on the server and in the local database.
    The ``--parent`` flag controls where the folder is created:

    * ``--parent user@gmail.com`` — root level of that account
    * ``--parent user@gmail.com/INBOX`` — under INBOX

    If ``--parent`` is omitted, the account must be derivable from the
    folder name's prefix (experimental), or the command will prompt via
    the interactive form.
    """
    svc: EmailService = get_email_service()

    if not remaining:
        raise CommandValidationError(
            "Missing folder name.",
            "Usage: !email folder add <name> [--parent {account}/{folder}]",
        )

    raw_name = " ".join(remaining).strip()

    # Resolve account and parent
    parent_flag = flags.get("parent", "")
    if parent_flag:
        account_email, parent_folder = _resolve_parent(parent_flag)
        folder_name = _build_folder_name(raw_name, parent_folder)
    else:
        raise CommandValidationError(
            "Missing --parent flag.",
            "Use --parent {account_email} for root-level, or "
            "--parent {account_email}/{parent_folder} for a subfolder.",
        )

    # Create on IMAP server
    try:
        _acct, client = _connect_imap(account_email, svc)
    except CommandValidationError:
        raise
    except Exception as e:
        raise CommandValidationError(f"Failed to connect to IMAP for {account_email}: {e}")

    try:
        success = client.create_folder(folder_name)
        if not success:
            raise CommandValidationError(
                f"IMAP CREATE failed for folder: {folder_name}",
            )
    finally:
        client.disconnect()

    # Insert into local DB
    from datetime import UTC as _UTC, datetime

    now = datetime.now(_UTC).isoformat()
    try:
        svc.db.execute(
            "INSERT OR IGNORE INTO folders "
            "(account_email, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (account_email, folder_name, now, now),
        )
    except Exception as e:
        raise CommandValidationError(
            f"Folder created on IMAP server but failed to save locally: {e}",
        )

    return {
        "type": "status",
        "title": "Folder Created",
        "data": {
            "account_email": account_email,
            "folder_name": folder_name,
            "parent": parent_folder or "(root level)",
        },
    }


@command("email.folder.rename")
def email_folder_rename(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email folder rename <path> <new_name>

    Rename an IMAP folder.  The path format is ``{account_email}/{folder}``.
    The *new_name* is the new simple name (not the full path).

    Example::
      !email folder rename user@gmail.com/MyFolder MyRenamedFolder
    """
    if not remaining or len(remaining) < 2:
        raise CommandValidationError(
            "Missing arguments.",
            "Usage: !email folder rename {account}/{folder} <new_name>",
        )

    raw_path = remaining[0]
    new_name = remaining[1]

    account_email, folder_name = _parse_folder_path(raw_path)

    # Build the new full path — keep same parent, change last segment
    parts = folder_name.rsplit("/", 1)
    if len(parts) > 1:
        new_full_name = f"{parts[0]}/{new_name}"
    else:
        new_full_name = new_name

    svc: EmailService = get_email_service()

    try:
        _acct, client = _connect_imap(account_email, svc)
    except CommandValidationError:
        raise
    except Exception as e:
        raise CommandValidationError(f"IMAP connection failed: {e}")

    try:
        success = client.rename_folder(folder_name, new_full_name)
        if not success:
            raise CommandValidationError(
                f"IMAP RENAME failed for folder: {folder_name} → {new_full_name}",
            )
    finally:
        client.disconnect()

    # Update local DB
    from datetime import UTC as _UTC, datetime

    now = datetime.now(_UTC).isoformat()
    svc.db.execute(
        "UPDATE folders SET name = ?, updated_at = ? "
        "WHERE account_email = ? AND name = ?",
        (new_full_name, now, account_email, folder_name),
    )

    return {
        "type": "status",
        "title": "Folder Renamed",
        "data": {
            "account_email": account_email,
            "old_name": folder_name,
            "new_name": new_full_name,
        },
    }


@command("email.folder.move")
def email_folder_move(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email folder move <path> --parent {account_email}[{/folder}]

    Move a folder to a different parent in the hierarchy (via IMAP RENAME).

    ``--parent`` specifies the new parent:
    * ``--parent user@gmail.com`` — move to root level of that account
    * ``--parent user@gmail.com/Archive`` — move under Archive

    The folder is moved with all its contents and sub-folders (IMAP RENAME
    is recursive).

    Examples::
      !email folder move user@gmail.com/MyFolder --parent user@gmail.com/Archive
      !email folder move user@gmail.com/MyFolder --parent user@gmail.com
    """
    if not remaining:
        raise CommandValidationError(
            "Missing folder path.",
            "Usage: !email folder move <path> --parent {account}[/{parent}]",
        )

    raw_path = remaining[0]
    parent_flag = flags.get("parent", "")
    if not parent_flag:
        raise CommandValidationError(
            "Missing --parent flag.",
            "Usage: !email folder move <path> --parent {account_email}/{parent_folder}",
        )

    account_email, folder_name = _parse_folder_path(raw_path)
    _parent_account, parent_folder = _resolve_parent(parent_flag)

    # Build the new full path
    # Extract the simple folder name (last segment)
    simple_name = folder_name.rsplit("/", 1)[-1]
    new_full_name = _build_folder_name(simple_name, parent_folder)

    svc: EmailService = get_email_service()

    try:
        _acct, client = _connect_imap(account_email, svc)
    except CommandValidationError:
        raise
    except Exception as e:
        raise CommandValidationError(f"IMAP connection failed: {e}")

    try:
        success = client.rename_folder(folder_name, new_full_name)
        if not success:
            raise CommandValidationError(
                f"IMAP RENAME failed for folder: {folder_name} → {new_full_name}",
            )
    finally:
        client.disconnect()

    # Update local DB
    from datetime import UTC as _UTC, datetime

    now = datetime.now(_UTC).isoformat()
    svc.db.execute(
        "UPDATE folders SET name = ?, updated_at = ? "
        "WHERE account_email = ? AND name = ?",
        (new_full_name, now, account_email, folder_name),
    )

    return {
        "type": "status",
        "title": "Folder Moved",
        "data": {
            "account_email": account_email,
            "old_path": folder_name,
            "new_path": new_full_name,
        },
    }


@command("email.folder.delete", permission_level=PermissionLevel.DESTRUCTIVE)
def email_folder_delete(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!email folder delete <path>

    Delete an IMAP folder from the server and local DB. The folder must
    be empty on most IMAP servers.

    Path format: ``{account_email}/{folder}``

    Example::
      !email folder delete user@gmail.com/OldFolder
    """
    if not remaining:
        raise CommandValidationError(
            "Missing folder path.",
            "Usage: !email folder delete {account}/{folder}",
        )

    raw_path = " ".join(remaining).strip()
    account_email, folder_name = _parse_folder_path(raw_path)

    svc: EmailService = get_email_service()

    try:
        _acct, client = _connect_imap(account_email, svc)
    except CommandValidationError:
        raise
    except Exception as e:
        raise CommandValidationError(f"IMAP connection failed: {e}")

    try:
        success = client.delete_folder(folder_name)
        if not success:
            raise CommandValidationError(
                f"IMAP DELETE failed for folder: {folder_name}. "
                "The folder must be empty on most IMAP servers.",
            )
    finally:
        client.disconnect()

    # Remove from local DB (messages within get folder_name set to NULL via FK)
    svc.db.execute(
        "DELETE FROM folders WHERE account_email = ? AND name = ?",
        (account_email, folder_name),
    )

    return {
        "type": "status",
        "title": "Folder Deleted",
        "data": {
            "account_email": account_email,
            "folder_name": folder_name,
        },
    }
