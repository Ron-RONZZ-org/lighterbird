"""Seed dummy email messages into an email.db for E2E testing.

Usage:
    python tests/seed_e2e_messages.py <data_dir>

Inserts 3 test messages with imap_uid=NULL (local-only, no IMAP sync)
into the first account found in email.db.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path


def seed_email_messages(data_dir: str) -> str:
    """Insert test messages into email.db.

    Args:
        data_dir: Path to the lighterbird data directory containing email.db.

    Returns:
        The email address of the account messages were inserted into.
    """
    db_path = Path(data_dir) / "email.db"
    if not db_path.exists():
        print(f"email.db not found at {db_path}")
        sys.exit(1)

    import sqlite3

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    account = conn.execute(
        "SELECT email FROM accounts ORDER BY sort_order LIMIT 1"
    ).fetchone()

    if not account:
        print("No email account found in DB")
        sys.exit(1)

    account_email = account["email"]
    now = datetime.now(UTC).isoformat()

    messages = [
        {
            "uuid": "e2e-test-msg-000000001",
            "account_email": account_email,
            "folder_name": "INBOX",
            "subject": "E2E Test Message 1",
            "from_addr": "sender@example.com",
            "to_recipients": json.dumps([account_email]),
            "body": "This is the first test message for E2E testing.",
            "received_at": now,
            "is_read": 0,
            "is_deleted": 0,
            "is_spam": 0,
        },
        {
            "uuid": "e2e-test-msg-000000002",
            "account_email": account_email,
            "folder_name": "INBOX",
            "subject": "E2E Test Message 2",
            "from_addr": "friend@example.com",
            "to_recipients": json.dumps([account_email]),
            "body": "This is the second test message -- unread.",
            "received_at": now,
            "is_read": 0,
            "is_deleted": 0,
            "is_spam": 0,
        },
        {
            "uuid": "e2e-test-msg-000000003",
            "account_email": account_email,
            "folder_name": "INBOX",
            "subject": "E2E Test Message 3",
            "from_addr": "spammer@spam.com",
            "to_recipients": json.dumps([account_email]),
            "body": "Buy cheap stuff! This is spam.",
            "received_at": now,
            "is_read": 0,
            "is_deleted": 0,
            "is_spam": 0,
        },
    ]

    for msg in messages:
        conn.execute(
            """INSERT OR IGNORE INTO messages
               (uuid, account_email, folder_name, subject, from_addr,
                to_recipients, body, received_at, is_read, is_deleted, is_spam)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg["uuid"], msg["account_email"], msg["folder_name"],
                msg["subject"], msg["from_addr"],
                msg["to_recipients"], msg["body"], msg["received_at"],
                msg["is_read"], msg["is_deleted"], msg["is_spam"],
            ),
        )

    conn.commit()
    conn.close()
    print(f"Seeded 3 messages into account {account_email}")
    return account_email


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tests/seed_e2e_messages.py <data_dir>")
        sys.exit(1)
    seed_email_messages(sys.argv[1])
