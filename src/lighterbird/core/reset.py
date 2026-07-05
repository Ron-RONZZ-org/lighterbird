"""Reset lighterbird to a fresh state with optional backup.

Typical usage::

    from lighterbird.core.reset import reset_to_fresh_state

    # Reset with backup (recommended)
    reset_to_fresh_state(backup_path=Path("/tmp/lighterbird-backup.7z"))

    # Reset without backup (irreversible!)
    reset_to_fresh_state()

The function performs a coordinated teardown across all domains:

1. Collect known email addresses and calendar UUIDs (for keyring cleanup)
2. Optionally create a 7z backup archive at the given path
3. Close all active DB connections via ``reset_services()``
4. Delete all ``*.db`` files from ``data_dir()``
5. Clear known keyring entries (passwords, LLM config)
6. Recreate schemas by calling each module's ``get_db()``
7. Re-protect directories with sentinel files
"""

from __future__ import annotations

import shutil
from datetime import UTC
from pathlib import Path
from typing import Any

from lighterbird.core.keyring import delete_password
from lighterbird.core.paths import data_dir, ensure_dirs

# ── Known keyring services ────────────────────────────────────────────────

_LLM_SERVICE = "lighterbird-llm"
_LLM_KEY = "active-provider"
_EMAIL_SERVICE_PREFIX = "lighterbird/email"
_CALENDAR_SERVICE_PREFIX = "lighterbird/calendar"
_KEYRING_PASSWORD_KEY = "password"


def _collect_known_accounts() -> dict[str, list[str]]:
    """Query existing databases for email addresses and calendar UUIDs.

    Returns:
        Dict with keys ``"emails"`` and ``"calendar_uuids"``.
        Returns empty lists if a database doesn't exist or can't be read.
    """
    emails: list[str] = []
    calendar_uuids: list[str] = []

    # Email accounts
    email_db = data_dir() / "email.db"
    if email_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(email_db), timeout=3.0)
            for row in conn.execute("SELECT email FROM accounts"):
                emails.append(row[0])
            conn.close()
        except sqlite3.Error:
            pass

    # Calendar accounts
    cal_db = data_dir() / "calendar.db"
    if cal_db.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(cal_db), timeout=3.0)
            for row in conn.execute("SELECT uuid FROM calendars"):
                calendar_uuids.append(row[0])
            conn.close()
        except sqlite3.Error:
            pass

    return {"emails": emails, "calendar_uuids": calendar_uuids}


def _clear_known_passwords(
    emails: list[str],
    calendar_uuids: list[str],
) -> int:
    """Clear keyring entries for known accounts and LLM config.

    Returns:
        Number of entries attempted to delete.
    """
    cleared = 0

    # LLM config
    if delete_password(_LLM_SERVICE, _LLM_KEY):
        cleared += 1

    # Email passwords
    for email in emails:
        svc = f"{_EMAIL_SERVICE_PREFIX}/{email}"
        if delete_password(svc, _KEYRING_PASSWORD_KEY):
            cleared += 1

    # Calendar passwords
    for cal_uuid in calendar_uuids:
        svc = f"{_CALENDAR_SERVICE_PREFIX}/{cal_uuid}"
        if delete_password(svc, _KEYRING_PASSWORD_KEY):
            cleared += 1

    return cleared


def _recreate_schemas() -> list[str]:
    """Re-initialise all database schemas in data_dir().

    Calls each module's ``get_db()`` which creates tables via
    ``CREATE TABLE IF NOT EXISTS``.  Returns list of created databases.
    """
    created: list[str] = []

    # email
    from lighterbird.email.db import get_db as email_get_db
    email_get_db()
    created.append("email.db")

    # calendar
    from lighterbird.calendar.db import get_db as cal_get_db
    cal_get_db()
    created.append("calendar.db")

    # contacts
    from lighterbird.contacts.db import get_db as contacts_get_db
    contacts_get_db()
    created.append("contacts.db")

    # todo
    from lighterbird.todo.db import get_db as todo_get_db
    todo_get_db()
    created.append("todo.db")

    # journal
    from lighterbird.journal.db import get_db as journal_get_db
    journal_get_db()
    created.append("journal.db")

    # letters
    from lighterbird.letter.db import get_db as letter_get_db
    letter_get_db()
    created.append("letters.db")

    # profiles
    from lighterbird.profiles.db import get_db as profiles_get_db
    profiles_get_db()
    created.append("profiles.db")

    # user_commands
    from lighterbird.user_commands.db import get_db as uc_get_db
    uc_get_db()
    created.append("user_commands.db")

    # tags
    from lighterbird.tags.db import get_db as tags_get_db
    tags_get_db()
    created.append("tags.db")

    return created


def reset_to_fresh_state(
    backup_path: str | Path | None = None,
) -> dict[str, Any]:
    """Reset lighterbird to a fresh (empty) state.

    Args:
        backup_path: Optional path to create a 7z backup archive before
            resetting.  If the path points to an existing directory, a
            filename is auto-generated as ``reset-{timestamp}.7z``.
            If ``None``, no backup is created.

    Returns:
        Dict with keys:

        - **backup_path** (:class:`str` | ``None``) — Path of created backup
        - **databases_removed** (:class:`list[str]`) — DB filenames deleted
        - **credentials_cleared** (:class:`int`) — Number of keyring entries
        - **schema_recreated** (:class:`list[str]`) — DB filenames recreated

    Raises:
        FileNotFoundError: If *backup_path* points to a non-existent parent
            directory.
        OSError: If backup creation or file deletion fails.
    """
    # Step 0: Collect known accounts BEFORE deleting DBs
    accounts = _collect_known_accounts()
    emails = accounts["emails"]
    cal_uuids = accounts["calendar_uuids"]

    # Step 1: Optionally create backup archive
    created_backup: str | None = None
    if backup_path is not None:
        backup = Path(backup_path)
        if backup.is_dir():
            # Auto-generate filename
            from datetime import datetime
            ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
            backup = backup / f"reset-{ts}.7z"
        # Ensure parent exists
        backup.parent.mkdir(parents=True, exist_ok=True)

        from lighterbird.core.backup import _checkpoint_known_dbs
        _checkpoint_known_dbs()

        # Create archive using the existing infrastructure
        from lighterbird.core.backup import _create_strategy_archive
        strategy = {"id": "reset", "max_copies": 1, "target": "local"}
        archive_path = _create_strategy_archive(strategy)
        if archive_path and archive_path.exists():
            # Move to user-specified path
            shutil.move(str(archive_path), str(backup))
            created_backup = str(backup.resolve())
        else:
            # Fallback: create archive directly at target
            import py7zr

            from lighterbird.core.backup import _known_config_files, _known_db_paths
            with py7zr.SevenZipFile(
                backup, mode="w", filters=[{"id": py7zr.FILTER_LZMA2}]
            ) as arc:
                for dbp in _known_db_paths():
                    arc.write(dbp, dbp.name)
                for cfp in _known_config_files():
                    arc.write(cfp, f"config/{cfp.name}")
            created_backup = str(backup.resolve())

    # Step 2: Close all DB connections
    from lighterbird.server.deps import reset_services
    reset_services()

    # Step 3: Delete all .db files in data_dir()
    ddir = data_dir()
    removed: list[str] = []
    for db_file in sorted(ddir.glob("*.db")):
        db_file.unlink(missing_ok=True)
        removed.append(db_file.name)

    # Step 4: Clear known keyring entries
    cleared = _clear_known_passwords(emails, cal_uuids)

    # Step 5: Recreate schemas
    created_dbs = _recreate_schemas()

    # Step 6: Re-protect directories
    ensure_dirs()

    return {
        "backup_path": created_backup,
        "databases_removed": removed,
        "credentials_cleared": cleared,
        "schema_recreated": created_dbs,
    }
