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
    uuid            TEXT PRIMARY KEY,
    ordo            INTEGER NOT NULL DEFAULT 0,
    nomo            TEXT NOT NULL,
    retposto        TEXT NOT NULL UNIQUE,
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
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid        TEXT NOT NULL UNIQUE,
    konto_id    TEXT NOT NULL REFERENCES kontoj(uuid) ON DELETE CASCADE,
    nomo        TEXT NOT NULL,
    patro_id    TEXT REFERENCES dosierujoj(uuid) ON DELETE CASCADE,
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL,
    UNIQUE(konto_id, nomo, patro_id)
);
"""

_CREATE_MESAGOJ = """
CREATE TABLE IF NOT EXISTS mesagoj (
    uuid           TEXT PRIMARY KEY,
    konto_id       TEXT NOT NULL REFERENCES kontoj(uuid) ON DELETE CASCADE,
    dosierujo_id   TEXT REFERENCES dosierujoj(uuid) ON DELETE SET NULL,
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
    modifita_je    TEXT NOT NULL
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
    uuid        TEXT PRIMARY KEY,
    nomo        TEXT NOT NULL UNIQUE,
    content     TEXT NOT NULL DEFAULT '',
    system      INTEGER NOT NULL DEFAULT 0,
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_SIEVE_AKTIVADOJ = """
CREATE TABLE IF NOT EXISTS sieve_aktivadoj (
    uuid         TEXT PRIMARY KEY,
    skripto_uuid TEXT NOT NULL REFERENCES sieve_skriptoj(uuid) ON DELETE CASCADE,
    konto_id     TEXT NOT NULL REFERENCES kontoj(uuid) ON DELETE CASCADE,
    active       INTEGER NOT NULL DEFAULT 0,
    man_sync     INTEGER NOT NULL DEFAULT 1,
    kreita_je    TEXT NOT NULL,
    modifita_je  TEXT NOT NULL,
    UNIQUE(skripto_uuid, konto_id)
);
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

# Migrate old per-account sieve_skriptoj to global + activations
_MIGRATE_SIEVE_GLOBAL = """
INSERT OR IGNORE INTO sieve_skriptoj (uuid, nomo, content, system, kreita_je, modifita_je)
SELECT uuid, nomo, content, system, kreita_je, modifita_je FROM sieve_skriptoj_old
WHERE nomo != '_spam_blocks';
"""
_MIGRATE_SIEVE_ACTIVATIONS = """
INSERT OR IGNORE INTO sieve_aktivadoj (uuid, skripto_uuid, konto_id, active, man_sync, kreita_je, modifita_je)
SELECT s.uuid || '_' || o.konto_id, s.uuid, o.konto_id, o.active, o.man_sync, o.kreita_je, o.modifita_je
FROM sieve_skriptoj_old o JOIN sieve_skriptoj s ON s.nomo = o.nomo
WHERE o.nomo != '_spam_blocks';
"""

_IDX_SIEVE_AKTIVADOJ_SKRIPTO = "CREATE INDEX IF NOT EXISTS idx_sieve_aktivadoj_skripto ON sieve_aktivadoj(skripto_uuid);"
_IDX_SIEVE_AKTIVADOJ_KONTO = "CREATE INDEX IF NOT EXISTS idx_sieve_aktivadoj_konto ON sieve_aktivadoj(konto_id);"

_IDX_MESAGOJ_KONTO = "CREATE INDEX IF NOT EXISTS idx_mesagoj_konto ON mesagoj(konto_id);"
_IDX_MESAGOJ_DOSIERUJO = "CREATE INDEX IF NOT EXISTS idx_mesagoj_dosierujo ON mesagoj(dosierujo_id);"
_IDX_MESAGOJ_IMAP_UID = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_mesagoj_imap_uid
    ON mesagoj(konto_id, dosierujo_id, imap_uid)
    WHERE imap_uid IS NOT NULL;
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
    _IDX_MESAGOJ_KONTO,
    _IDX_MESAGOJ_DOSIERUJO,
    _IDX_MESAGOJ_IMAP_UID,
    _IDX_MESAGOJ_DATO,
    _IDX_ALDONAĴOJ_MESAGO,
    _IDX_SIEVE_AKTIVADOJ_SKRIPTO,
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

    # ── Migration: old per-account sieve_skriptoj → global + activations ──
    # The old table (v1) had konto_id, active, man_sync columns.
    # We rename it to sieve_skriptoj_v1, create new tables, migrate data.
    # If migration already ran (v2), the new schema is already in place.
    try:
        col_info = db.execute("PRAGMA table_info(sieve_skriptoj)")
        columns = {row["name"] for row in col_info}
        if "konto_id" in columns:
            # V1 schema detected — migrate
            db.execute("DROP TABLE IF EXISTS sieve_skriptoj_v1")
            db.execute("ALTER TABLE sieve_skriptoj RENAME TO sieve_skriptoj_v1")
            # Create new tables (they may already exist with IF NOT EXISTS,
            # but we just renamed the old one, so they need recreation)
            db.execute("DROP TABLE IF EXISTS sieve_skriptoj")
            db.execute(_CREATE_SIEVE_SKRIPTOJ)
            db.execute("DROP TABLE IF EXISTS sieve_aktivadoj")
            db.execute(_CREATE_SIEVE_AKTIVADOJ)
            # Migrate data (excluding _spam_blocks — per-account system scripts)
            db.execute(_MIGRATE_SIEVE_GLOBAL)
            db.execute(_MIGRATE_SIEVE_ACTIVATIONS)
            db.execute("DROP TABLE sieve_skriptoj_v1")
            # Create indexes
            db.execute(_IDX_SIEVE_AKTIVADOJ_SKRIPTO)
            db.execute(_IDX_SIEVE_AKTIVADOJ_KONTO)
    except OperationalError:
        pass  # No migration needed (fresh install or already migrated)

    return db
