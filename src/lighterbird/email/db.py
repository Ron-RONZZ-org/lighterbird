"""Email database schema and initialization.

Schema includes: accounts, folders, messages, attachments.
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_ACCOUNTS = """
CREATE TABLE IF NOT EXISTS accounts (
    email            TEXT PRIMARY KEY COLLATE NOCASE
                     CHECK(email LIKE '%_@%_.__%'),
    sort_order       INTEGER NOT NULL DEFAULT 0,
    name             TEXT NOT NULL,
    imap_server      TEXT NOT NULL,
    imap_port        INTEGER NOT NULL DEFAULT 993,
    imap_use_ssl     INTEGER NOT NULL DEFAULT 1,
    smtp_server      TEXT NOT NULL,
    smtp_port        INTEGER NOT NULL DEFAULT 587,
    smtp_use_tls     INTEGER NOT NULL DEFAULT 1,
    imap_username    TEXT,
    smtp_username    TEXT,
    signature        TEXT NOT NULL DEFAULT '',
    auth_type        TEXT NOT NULL DEFAULT 'password',
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);
"""

_CREATE_FOLDERS = """
CREATE TABLE IF NOT EXISTS folders (
    account_email TEXT NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,
    name          TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (account_email, name)
);
"""

_CREATE_MESSAGES = """
CREATE TABLE IF NOT EXISTS messages (
    uuid              TEXT PRIMARY KEY,
    account_email     TEXT NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,
    folder_name       TEXT,
    message_id        TEXT,
    in_reply_to       TEXT,
    imap_uid          INTEGER,
    from_addr         TEXT,
    to_recipients     TEXT NOT NULL DEFAULT '[]',
    cc_recipients     TEXT NOT NULL DEFAULT '[]',
    subject           TEXT,
    body              TEXT,
    html_body         TEXT,
    priority          INTEGER DEFAULT 5,
    is_read           INTEGER NOT NULL DEFAULT 0,
    is_starred        INTEGER NOT NULL DEFAULT 0,
    is_deleted        INTEGER NOT NULL DEFAULT 0,
    received_at       TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    FOREIGN KEY (account_email, folder_name) REFERENCES folders(account_email, name) ON DELETE SET NULL
);
"""

_CREATE_ATTACHMENTS = """
CREATE TABLE IF NOT EXISTS email_attachments (
    uuid            TEXT PRIMARY KEY,
    message_uuid    TEXT NOT NULL REFERENCES messages(uuid) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    mime_type       TEXT NOT NULL DEFAULT 'application/octet-stream',
    size            INTEGER NOT NULL DEFAULT 0,
    content_id      TEXT NOT NULL,
    storage_path    TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

_CREATE_SPAM_BLOCKS = """
CREATE TABLE IF NOT EXISTS spam_blocks (
    uuid        TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    pattern     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

_CREATE_SIEVE_SCRIPTS = """
CREATE TABLE IF NOT EXISTS sieve_scripts (
    name        TEXT PRIMARY KEY,
    content     TEXT NOT NULL DEFAULT '',
    system      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

_CREATE_SIEVE_ACTIVATIONS = """
CREATE TABLE IF NOT EXISTS sieve_activations (
    script_name TEXT NOT NULL REFERENCES sieve_scripts(name) ON DELETE CASCADE,
    account_email TEXT NOT NULL REFERENCES accounts(email) ON DELETE CASCADE,
    active       INTEGER NOT NULL DEFAULT 0,
    priority     INTEGER NOT NULL DEFAULT 0,
    man_sync     INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (script_name, account_email)
);
"""

_MIGRATE_SIEVE_ACTIVATIONS_PRIORITY = """
ALTER TABLE sieve_activations ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;
"""

_MIGRATE_ACCOUNTS_MANAGESIEVE = """
ALTER TABLE accounts ADD COLUMN managesieve_host TEXT NOT NULL DEFAULT '';
"""
_MIGRATE_ACCOUNTS_MANAGESIEVE_PORT = """
ALTER TABLE accounts ADD COLUMN managesieve_port INTEGER NOT NULL DEFAULT 4190;
"""
_MIGRATE_ACCOUNTS_MANAGESIEVE_TLS = """
ALTER TABLE accounts ADD COLUMN managesieve_use_tls INTEGER NOT NULL DEFAULT 1;
"""

_WRITING_SAMPLES_TABLE = """
CREATE TABLE IF NOT EXISTS writing_samples (
    uuid            TEXT PRIMARY KEY,
    source_uuid     TEXT NOT NULL,
    source_domain   TEXT NOT NULL DEFAULT 'email',
    title           TEXT,
    body            TEXT NOT NULL,
    body_format     TEXT DEFAULT 'markdown',
    language        TEXT DEFAULT 'en',
    word_count      INTEGER DEFAULT 0,
    embedding_dim   INTEGER,
    registered_at   TEXT NOT NULL
);
"""

_DROP_LEGACY_ALDONAJXOJ = "DROP TABLE IF EXISTS aldonajxoj;"

_SYNC_BACKLOG_TABLE = """
CREATE TABLE IF NOT EXISTS _sync_backlog (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_uuid        TEXT NOT NULL,
    account_email   TEXT NOT NULL,
    folder_name     TEXT,
    imap_uid        INTEGER,
    is_read         INTEGER NOT NULL DEFAULT 0,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    last_attempt    TEXT,
    retries         INTEGER NOT NULL DEFAULT 0
);
"""
_IDX_SYNC_BACKLOG_MSG = "CREATE INDEX IF NOT EXISTS idx_sync_backlog_msg ON _sync_backlog(msg_uuid);"

_IDX_SIEVE_ACTIVATIONS_ACCOUNT = "CREATE INDEX IF NOT EXISTS idx_sieve_activations_account ON sieve_activations(account_email);"

_IDX_MESSAGES_ACCOUNT = "CREATE INDEX IF NOT EXISTS idx_messages_account ON messages(account_email);"
_IDX_MESSAGES_FOLDER = "CREATE INDEX IF NOT EXISTS idx_messages_folder ON messages(account_email, folder_name);"
_IDX_MESSAGES_IMAP_UID = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_imap_uid
    ON messages(account_email, folder_name, imap_uid)
    WHERE imap_uid IS NOT NULL;
"""
_IDX_MESSAGES_MESSAGE_ID = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_message_id
    ON messages(account_email, message_id)
    WHERE message_id IS NOT NULL;
"""
_SEND_QUEUE_TABLE = """
CREATE TABLE IF NOT EXISTS send_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_uuid        TEXT NOT NULL UNIQUE REFERENCES messages(uuid) ON DELETE CASCADE,
    account_email   TEXT NOT NULL,
    body_format     TEXT NOT NULL DEFAULT 'markdown',
    signature       TEXT NOT NULL DEFAULT '',
    priority        INTEGER NOT NULL DEFAULT 3,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'running', 'completed', 'failed')),
    retries         INTEGER NOT NULL DEFAULT 0,
    max_retries     INTEGER NOT NULL DEFAULT 10,
    next_attempt    TEXT,
    last_error      TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""
_IDX_SEND_QUEUE_STATUS = "CREATE INDEX IF NOT EXISTS idx_send_queue_status ON send_queue(status, next_attempt);"

_IDX_MESSAGES_DATE = "CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(received_at);"
_IDX_ATTACHMENTS_MESSAGE = "CREATE INDEX IF NOT EXISTS idx_email_attachments_message ON email_attachments(message_uuid);"

_SCHEMA_STATEMENTS: list[str] = [
    _CREATE_ACCOUNTS,
    _CREATE_FOLDERS,
    _CREATE_MESSAGES,
    _CREATE_ATTACHMENTS,
    _WRITING_SAMPLES_TABLE,
    _DROP_LEGACY_ALDONAJXOJ,
    _SYNC_BACKLOG_TABLE,
    _SEND_QUEUE_TABLE,
    _CREATE_SPAM_BLOCKS,
    _CREATE_SIEVE_SCRIPTS,
    _CREATE_SIEVE_ACTIVATIONS,
    _MIGRATE_ACCOUNTS_MANAGESIEVE,
    _MIGRATE_ACCOUNTS_MANAGESIEVE_PORT,
    _MIGRATE_ACCOUNTS_MANAGESIEVE_TLS,
    _MIGRATE_SIEVE_ACTIVATIONS_PRIORITY,
    _IDX_MESSAGES_ACCOUNT,
    _IDX_MESSAGES_FOLDER,
    _IDX_MESSAGES_IMAP_UID,
    _IDX_MESSAGES_MESSAGE_ID,
    _IDX_MESSAGES_DATE,
    _IDX_ATTACHMENTS_MESSAGE,
    _IDX_SYNC_BACKLOG_MSG,
    _IDX_SIEVE_ACTIVATIONS_ACCOUNT,
    _IDX_SEND_QUEUE_STATUS,
]


def _email_db_path() -> Path:
    return data_dir() / "email.db"


def _load_sqlite_vec(conn: sqlite3.Connection) -> None:
    """Load the sqlite-vec extension on a connection (best-effort)."""
    try:
        import sqlite_vec  # type: ignore[import-untyped]

        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
    except Exception:
        pass  # sqlite-vec not installed — writing samples work without vectors


def ensure_vec_table(db: LighterbirdDB, dim: int = 1536) -> None:
    """Create the ``vec_samples`` virtual table if it does not exist.

    Safe to call multiple times — the ``IF NOT EXISTS`` check is done
    at the SQL level.  The dimension is fixed at table creation time;
    changing it requires dropping and recreating the table.

    Args:
        db: Database connection.
        dim: Embedding dimensionality (default 1536 for OpenAI
            ``text-embedding-3-small``).
    """
    # Try vec0 first; fall back to a stub table if sqlite-vec not loaded
    try:
        db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_samples "
            f"USING vec0(embedding float[{dim}])"
        )
    except Exception:
        # sqlite-vec not loaded — create a stub so code doesn't crash
        db.execute(
            "CREATE TABLE IF NOT EXISTS vec_samples ("
            "  rowid INTEGER PRIMARY KEY"
            ")"
        )


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    """Get the email database connection with schema initialized."""
    from sqlite3 import OperationalError

    resolved = Path(path) if path else _email_db_path()
    db = LighterbirdDB(resolved, after_connect=_load_sqlite_vec)
    for stmt in _SCHEMA_STATEMENTS:
        try:
            db.execute(stmt)
        except OperationalError:
            if not stmt.strip().upper().startswith("ALTER"):
                raise

    return db
