"""Email database schema and initialization.

Forked from A-lien's data storage, simplified for MVP.
Schema includes: kontoj (accounts), dosierujoj (folders), mesagoj (messages),
aldonajxoj (attachments).
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

# ── DDL ─────────────────────────────────────────────────────────────────────

_CREATE_KONTOJ = """
CREATE TABLE IF NOT EXISTS kontoj (
    retposto        TEXT PRIMARY KEY COLLATE NOCASE
                    CHECK(retposto LIKE '%_@%_.__%'),
    ordo            INTEGER NOT NULL DEFAULT 0,
    nomo            TEXT NOT NULL,
    imap_servilo    TEXT NOT NULL,
    imap_haveno     INTEGER NOT NULL DEFAULT 993,
    imap_ssl        INTEGER NOT NULL DEFAULT 1,
    smtp_servilo    TEXT NOT NULL,
    smtp_haveno     INTEGER NOT NULL DEFAULT 587,
    smtp_tls        INTEGER NOT NULL DEFAULT 1,
    imap_uzantonomo TEXT,
    smtp_uzantonomo TEXT,
    subskribo       TEXT NOT NULL DEFAULT '',
    auth_type       TEXT NOT NULL DEFAULT 'password',
    kreita_je       TEXT NOT NULL,
    modifita_je     TEXT NOT NULL
);
"""

_CREATE_DOSIERUJOJ = """
CREATE TABLE IF NOT EXISTS dosierujoj (
    konto_id    TEXT NOT NULL REFERENCES kontoj(retposto) ON DELETE CASCADE,
    nomo        TEXT NOT NULL,
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL,
    PRIMARY KEY (konto_id, nomo)
);
"""

_CREATE_MESAGOJ = """
CREATE TABLE IF NOT EXISTS mesagoj (
    uuid           TEXT PRIMARY KEY,
    konto_id       TEXT NOT NULL REFERENCES kontoj(retposto) ON DELETE CASCADE,
    dosierujo_nomo TEXT,
    message_id     TEXT,
    in_reply_to    TEXT,
    imap_uid       INTEGER,
    de             TEXT,
    al             TEXT NOT NULL DEFAULT '[]',
    kc             TEXT NOT NULL DEFAULT '[]',
    subjekto       TEXT,
    korpo          TEXT,
    html_korpo     TEXT,
    prioritato     INTEGER DEFAULT 5,
    legita         INTEGER NOT NULL DEFAULT 0,
    stelo          INTEGER NOT NULL DEFAULT 0,
    forigita       INTEGER NOT NULL DEFAULT 0,
    ricevita_je    TEXT,
    kreita_je      TEXT NOT NULL,
    modifita_je    TEXT NOT NULL,
    FOREIGN KEY (konto_id, dosierujo_nomo) REFERENCES dosierujoj(konto_id, nomo) ON DELETE SET NULL
);
"""

_CREATE_ALDONAĴOJ = """
CREATE TABLE IF NOT EXISTS aldonajxoj (
    uuid            TEXT PRIMARY KEY,
    mesago_uuid     TEXT NOT NULL REFERENCES mesagoj(uuid) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    mime_type       TEXT NOT NULL DEFAULT 'application/octet-stream',
    size            INTEGER NOT NULL DEFAULT 0,
    content_id      TEXT NOT NULL,
    storage_path    TEXT NOT NULL,
    kreita_je       TEXT NOT NULL,
    modifita_je     TEXT NOT NULL
);
"""

_CREATE_SPAM_BLOKOJ = """
CREATE TABLE IF NOT EXISTS spam_blockoj (
    uuid        TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    pattern     TEXT NOT NULL,
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_SIEVE_SKRIPTOJ = """
CREATE TABLE IF NOT EXISTS sieve_skriptoj (
    nomo        TEXT PRIMARY KEY,
    content     TEXT NOT NULL DEFAULT '',
    system      INTEGER NOT NULL DEFAULT 0,
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_SIEVE_AKTIVADOJ = """
CREATE TABLE IF NOT EXISTS sieve_aktivadoj (
    skripto_nomo TEXT NOT NULL REFERENCES sieve_skriptoj(nomo) ON DELETE CASCADE,
    konto_id     TEXT NOT NULL REFERENCES kontoj(retposto) ON DELETE CASCADE,
    active       INTEGER NOT NULL DEFAULT 0,
    priority     INTEGER NOT NULL DEFAULT 0,
    man_sync     INTEGER NOT NULL DEFAULT 1,
    kreita_je    TEXT NOT NULL,
    modifita_je  TEXT NOT NULL,
    PRIMARY KEY (skripto_nomo, konto_id)
);
"""

# Priority column migration for existing databases
_MIGRATE_SIEVE_AKTIVADOJ_PRIORITY = """
ALTER TABLE sieve_aktivadoj ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;
"""

# ManageSieve columns added to kontoj
_MIGRATE_KONTOJ_MANAGESIEVE = """
ALTER TABLE kontoj ADD COLUMN managesieve_host TEXT NOT NULL DEFAULT '';
"""
_MIGRATE_KONTOJ_MANAGESIEVE_PORT = """
ALTER TABLE kontoj ADD COLUMN managesieve_port INTEGER NOT NULL DEFAULT 4190;
"""
_MIGRATE_KONTOJ_MANAGESIEVE_TLS = """
ALTER TABLE kontoj ADD COLUMN managesieve_use_tls INTEGER NOT NULL DEFAULT 1;
"""

_IDX_SIEVE_AKTIVADOJ_KONTO = "CREATE INDEX IF NOT EXISTS idx_sieve_aktivadoj_konto ON sieve_aktivadoj(konto_id);"

_IDX_MESAGOJ_KONTO = "CREATE INDEX IF NOT EXISTS idx_mesagoj_konto ON mesagoj(konto_id);"
_IDX_MESAGOJ_DOSIERUJO = "CREATE INDEX IF NOT EXISTS idx_mesagoj_dosierujo ON mesagoj(konto_id, dosierujo_nomo);"
_IDX_MESAGOJ_IMAP_UID = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_mesagoj_imap_uid
    ON mesagoj(konto_id, dosierujo_nomo, imap_uid)
    WHERE imap_uid IS NOT NULL;
"""
_IDX_MESAGOJ_MESSAGE_ID = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_mesagoj_message_id
    ON mesagoj(konto_id, message_id)
    WHERE message_id IS NOT NULL;
"""
_IDX_MESAGOJ_DATO = "CREATE INDEX IF NOT EXISTS idx_mesagoj_dato ON mesagoj(ricevita_je);"
_IDX_ALDONAĴOJ_MESAGO = "CREATE INDEX IF NOT EXISTS idx_aldonajxoj_mesago ON aldonajxoj(mesago_uuid);"

_SCHEMA_STATEMENTS: list[str] = [
    _CREATE_KONTOJ,
    _CREATE_DOSIERUJOJ,
    _CREATE_MESAGOJ,
    _CREATE_ALDONAĴOJ,
    _CREATE_SPAM_BLOKOJ,
    _CREATE_SIEVE_SKRIPTOJ,
    _CREATE_SIEVE_AKTIVADOJ,
    _MIGRATE_KONTOJ_MANAGESIEVE,
    _MIGRATE_KONTOJ_MANAGESIEVE_PORT,
    _MIGRATE_KONTOJ_MANAGESIEVE_TLS,
    _MIGRATE_SIEVE_AKTIVADOJ_PRIORITY,
    _IDX_MESAGOJ_KONTO,
    _IDX_MESAGOJ_DOSIERUJO,
    _IDX_MESAGOJ_IMAP_UID,
    _IDX_MESAGOJ_MESSAGE_ID,
    _IDX_MESAGOJ_DATO,
    _IDX_ALDONAĴOJ_MESAGO,
    _IDX_SIEVE_AKTIVADOJ_KONTO,
]

# ── Database path ───────────────────────────────────────────────────────────


def _email_db_path() -> Path:
    return data_dir() / "email.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    """Get the email database connection with schema initialized."""
    from sqlite3 import OperationalError

    resolved = Path(path) if path else _email_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STATEMENTS:
        try:
            db.execute(stmt)
        except OperationalError:
            # ALTER TABLE ADD COLUMN may fail if column already exists
            # on an existing database. Other statements use IF NOT EXISTS
            # and are idempotent — re-raise unexpected errors.
            if not stmt.strip().upper().startswith("ALTER"):
                raise

    return db
