"""Seed email.db with test accounts from .dev credentials."""

from __future__ import annotations

from pathlib import Path

from lighterbird.scripts.seeders._helpers import _gen_uuid, _now


def _create_account(
    db, email: str, password: str, sort_order: int,
    creds: dict[str, str], now: str,
) -> None:
    """Insert a single email account and its folders."""
    from lighterbird.email.server_detect import detect_servers

    name = email.split("@")[0]
    try:
        detected = detect_servers(email)
    except Exception:
        detected = {
            "imap": f"imap.{email.split('@')[1]}",
            "smtp": f"smtp.{email.split('@')[1]}",
        }

    domain = email.split("@")[1]
    db.execute(
        """INSERT OR IGNORE INTO accounts
           (email, sort_order, name, imap_server, imap_port, imap_use_ssl,
            smtp_server, smtp_port, smtp_use_tls,
            imap_username, smtp_username,
            managesieve_host, managesieve_port, managesieve_use_tls,
            signature, auth_type, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            email, sort_order, name,
            detected.get("imap", f"imap.{domain}"), 993, 1,
            detected.get("smtp", f"smtp.{domain}"), 587, 1,
            email, email,
            detected.get("managesieve_host", ""),
            detected.get("managesieve_port", 4190), 1,
            "", "password", now, now,
        ),
    )

    if password:
        from lighterbird.email.keyring import set_password
        set_password(email, password)

    for folder in ("INBOX", "Sent", "Trash", "Spam", "Junk"):
        db.execute(
            "INSERT OR IGNORE INTO folders (account_email, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (email, folder, now, now),
        )


def _seed_email(data_dir: Path, creds: dict[str, str]) -> None:
    """Seed email.db with both test accounts from .dev credentials."""
    from lighterbird.email.db import get_db

    db_path = data_dir / "email.db"
    db = get_db(db_path)

    now = _now()

    # ── Account 1 ────────────────────────────────────────────────────────
    email1 = creds.get("TEST_EMAIL_1", "test1@example.com")
    pw1 = creds.get("TEST_EMAIL_1_PASS", "")
    _create_account(db, email1, pw1, 0, creds, now)

    # ── Account 2 ────────────────────────────────────────────────────────
    email2 = creds.get("TEST_EMAIL_2", "test2@example.com")
    pw2 = creds.get("TEST_EMAIL_2_PASS", "")
    _create_account(db, email2, pw2, 1, creds, now)

    # NOTE: Email messages are NOT seeded. Seeded messages have imap_uid=NULL,
    # which breaks read-status sync (backlog entries can't be processed) and
    # trash sync (_retry_pending_trash requires imap_uid IS NOT NULL).
    # Real messages fetched from the IMAP server during testing have proper
    # imap_uid values and work correctly with all flag-sync mechanisms.
