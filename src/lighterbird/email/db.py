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
    note        TEXT NOT NULL DEFAULT '',
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
    operation       TEXT NOT NULL DEFAULT 'sync',
    created_at      TEXT NOT NULL,
    last_attempt    TEXT,
    retries         INTEGER NOT NULL DEFAULT 0
);
"""
_IDX_SYNC_BACKLOG_MSG = "CREATE INDEX IF NOT EXISTS idx_sync_backlog_msg ON _sync_backlog(msg_uuid);"

_IDX_SIEVE_ACTIVATIONS_ACCOUNT = "CREATE INDEX IF NOT EXISTS idx_sieve_activations_account ON sieve_activations(account_email);"

# ── Multi-signature support (v2: decoupled from accounts) ─────────────
_EMAIL_SIGNATURES_TABLE = """
CREATE TABLE IF NOT EXISTS email_signatures (
    uuid              TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    signature_text    TEXT NOT NULL DEFAULT '',
    signature_format  TEXT NOT NULL DEFAULT 'plain'
                      CHECK(signature_format IN ('plain', 'html', 'markdown')),
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE(name)
);
"""
_MIGRATE_ACCOUNTS_DEFAULT_SIGNATURE = """
ALTER TABLE accounts ADD COLUMN default_signature_uuid TEXT REFERENCES email_signatures(uuid) ON DELETE SET NULL;
"""
_MIGRATE_SIGNATURE_FORMAT = """
ALTER TABLE email_signatures ADD COLUMN signature_format TEXT NOT NULL DEFAULT 'plain';
"""
_MIGRATE_SEND_QUEUE_SIGNATURE_FORMAT = """
ALTER TABLE send_queue ADD COLUMN signature_format TEXT NOT NULL DEFAULT 'plain';
"""

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
    WHERE message_id IS NOT NULL AND message_id != '';
"""
# Drop the old message_id index that included empty strings (causing
# spurious UNIQUE constraint violations for messages without Message-ID).
# Replaced by the corrected definition below.
_MIGRATE_DROP_OLD_MESSAGE_ID_IDX = """
DROP INDEX IF EXISTS idx_messages_message_id;
"""
_IDX_MESSAGES_MODSEQ = """
CREATE INDEX IF NOT EXISTS idx_messages_modseq
    ON messages(account_email, folder_name, modseq);
"""

_DEAD_LETTERS_TABLE = """
CREATE TABLE IF NOT EXISTS _dead_letters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_uuid        TEXT NOT NULL,
    account_email   TEXT NOT NULL,
    folder_name     TEXT,
    imap_uid        INTEGER,
    is_read         INTEGER NOT NULL DEFAULT 0,
    is_deleted      INTEGER NOT NULL DEFAULT 0,
    operation       TEXT NOT NULL DEFAULT 'sync',
    created_at      TEXT NOT NULL,
    last_attempt    TEXT NOT NULL,
    retries         INTEGER NOT NULL DEFAULT 0,
    dead_at         TEXT NOT NULL,
    reason          TEXT NOT NULL DEFAULT ''
);
"""
_IDX_DEAD_LETTERS_ACCOUNT = "CREATE INDEX IF NOT EXISTS idx_dead_letters_account ON _dead_letters(account_email);"

# ── CONDSTORE / UIDVALIDITY / SPECIAL-USE migrations ────────────────────
# All new columns are nullable with sensible defaults, backward-compatible.
_MIGRATE_MESSAGES_MODSEQ = """
ALTER TABLE messages ADD COLUMN modseq INTEGER;
"""

# ── Lazy body fetch / sync priority ──────────────────────────────────────
# body_fetched: 1=full body already downloaded, 0=only header synced
# sync_priority: lower = synced first (1 for special-use, 10 for custom)
_MIGRATE_MESSAGES_BODY_FETCHED = """
ALTER TABLE messages ADD COLUMN body_fetched INTEGER NOT NULL DEFAULT 1;
"""
_MIGRATE_FOLDERS_SYNC_PRIORITY = """
ALTER TABLE folders ADD COLUMN sync_priority INTEGER NOT NULL DEFAULT 10;
"""
_MIGRATE_FOLDERS_UIDVALIDITY = """
ALTER TABLE folders ADD COLUMN uidvalidity INTEGER;
"""
_MIGRATE_FOLDERS_HIGHEST_MODSEQ = """
ALTER TABLE folders ADD COLUMN highest_modseq INTEGER NOT NULL DEFAULT 0;
"""
_MIGRATE_FOLDERS_SPECIAL_USE = """
ALTER TABLE folders ADD COLUMN special_use TEXT;
"""
_MIGRATE_SYNC_BACKLOG_OPERATION = """
ALTER TABLE _sync_backlog ADD COLUMN operation TEXT NOT NULL DEFAULT 'sync';
"""
_MIGRATE_DEAD_LETTERS_OPERATION = """
ALTER TABLE _dead_letters ADD COLUMN operation TEXT NOT NULL DEFAULT 'sync';
"""

_SEND_QUEUE_TABLE = """
CREATE TABLE IF NOT EXISTS send_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_uuid        TEXT NOT NULL UNIQUE REFERENCES messages(uuid) ON DELETE CASCADE,
    account_email   TEXT NOT NULL,
    body_format     TEXT NOT NULL DEFAULT 'markdown',
    signature       TEXT NOT NULL DEFAULT '',
    signature_format TEXT NOT NULL DEFAULT 'plain',
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

# ── Email Draft UID Map (Phase 0: IMAP draft sync) ─────────────────────
_EMAIL_DRAFT_UID_MAP_TABLE = """
CREATE TABLE IF NOT EXISTS email_draft_uid_map (
    account_email  TEXT NOT NULL,
    folder_name    TEXT NOT NULL,
    draft_uuid     TEXT NOT NULL,
    imap_uid       INTEGER,
    message_id     TEXT,
    sent_local     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (account_email, folder_name, draft_uuid)
);
"""
_IDX_DRAFT_UID_MAP_IMAP_UID = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_draft_uid_map_imap_uid
    ON email_draft_uid_map(account_email, folder_name, imap_uid);
"""

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
    # CONDSTORE / UIDVALIDITY / SPECIAL-USE (Phase 0 of IMAP sync overhaul)
    _MIGRATE_MESSAGES_MODSEQ,
    _MIGRATE_FOLDERS_UIDVALIDITY,
    _MIGRATE_FOLDERS_HIGHEST_MODSEQ,
    _MIGRATE_FOLDERS_SPECIAL_USE,
    _DEAD_LETTERS_TABLE,
    # Lazy body fetch / sync priority
    _MIGRATE_MESSAGES_BODY_FETCHED,
    _MIGRATE_FOLDERS_SYNC_PRIORITY,
    _IDX_MESSAGES_ACCOUNT,
    _IDX_MESSAGES_FOLDER,
    _IDX_MESSAGES_IMAP_UID,
    _MIGRATE_DROP_OLD_MESSAGE_ID_IDX,  # Drop then recreate to fix WHERE clause
    _IDX_MESSAGES_MESSAGE_ID,
    _IDX_MESSAGES_MODSEQ,
    _IDX_MESSAGES_DATE,
    _IDX_ATTACHMENTS_MESSAGE,
    _MIGRATE_SYNC_BACKLOG_OPERATION,
    _MIGRATE_DEAD_LETTERS_OPERATION,
    _IDX_SYNC_BACKLOG_MSG,
    _IDX_DEAD_LETTERS_ACCOUNT,
    _IDX_SIEVE_ACTIVATIONS_ACCOUNT,
    # Draft UID mapping (Phase 0: IMAP draft sync)
    _EMAIL_DRAFT_UID_MAP_TABLE,
    _IDX_DRAFT_UID_MAP_IMAP_UID,
    # Multi-signature (Phase 2: decoupled from accounts)
    _MIGRATE_ACCOUNTS_DEFAULT_SIGNATURE,
    _MIGRATE_SIGNATURE_FORMAT,
    _MIGRATE_SEND_QUEUE_SIGNATURE_FORMAT,
    _EMAIL_SIGNATURES_TABLE,
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


def _migrate_existing_signatures(db: LighterbirdDB) -> None:
    """Copy existing per-account signatures from accounts table to email_signatures.

    Runs once; subsequent calls are no-ops because of INSERT OR IGNORE.
    The existing signature on an account becomes the ``default`` named signature
    for that account.
    """
    import uuid

    rows = list(db.execute(
        "SELECT email, signature, created_at, updated_at FROM accounts "
        "WHERE signature != ''"
    ))
    for row in rows:
        try:
            db.execute(
                "INSERT OR IGNORE INTO email_signatures "
                "(uuid, name, signature_text, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), row["email"] + " (default)",
                 row["signature"], row.get("created_at", ""), row.get("updated_at", "")),
            )
        except Exception:
            pass  # best-effort migration


def _migrate_signatures_v2(db: LighterbirdDB) -> None:
    """Migrate from per-account signatures (Phase 1) to global signatures (Phase 2).

    Handles the transition where ``email_signatures`` still has the
    ``account_email`` column (old schema). Renames the old table, creates
    the new one, and copies data over with name deduplication.
    Safe to call multiple times — idempotent via IF NOT EXISTS.
    """
    import uuid as _uuid
    from datetime import UTC, datetime

    # Check if old table exists with account_email column
    try:
        old_rows = list(db.execute(
            "SELECT uuid, account_email, name, signature_text, created_at, updated_at "
            "FROM email_signatures LIMIT 1"
        ))
    except Exception:
        return  # Table doesn't exist yet — nothing to migrate

    # If we got here, the old table exists but may have the new schema.
    # Check if account_email column still exists.
    try:
        db.execute("SELECT account_email FROM email_signatures LIMIT 0")
        has_account_email = True
    except Exception:
        has_account_email = False

    if not has_account_email:
        return  # Already migrated

    # Rename old table
    db.execute("ALTER TABLE email_signatures RENAME TO email_signatures_old")

    # Create new table (IF NOT EXISTS so the CREATE TABLE from _SCHEMA_STATEMENTS wins)
    db.execute("""
        CREATE TABLE IF NOT EXISTS email_signatures (
            uuid            TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            signature_text  TEXT NOT NULL DEFAULT '',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            UNIQUE(name)
        )
    """)

    # Copy data — handle name conflicts by appending email local-part
    old_data = list(db.execute(
        "SELECT uuid, account_email, name, signature_text, created_at, updated_at "
        "FROM email_signatures_old ORDER BY created_at ASC"
    ))
    seen_names: set[str] = set()
    for row in old_data:
        name = row["name"]
        if name in seen_names:
            local_part = row["account_email"].split("@")[0] if "@" in row["account_email"] else "acct"
            name = f"{name}-{local_part}"
        if name in seen_names:
            name = f"{name}-{_uuid.uuid4().hex[:4]}"
        seen_names.add(name)
        try:
            db.execute(
                "INSERT OR IGNORE INTO email_signatures "
                "(uuid, name, signature_text, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (row["uuid"], name,
                 row["signature_text"], row["created_at"], row["updated_at"]),
            )
        except Exception:
            pass

    # Drop old table
    try:
        db.execute("DROP TABLE IF EXISTS email_signatures_old")
    except Exception:
        pass


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

    _migrate_existing_signatures(db)
    _migrate_signatures_v2(db)
    return db
