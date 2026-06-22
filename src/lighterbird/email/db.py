"""Email database schema and initialization.

Forked from A-lien's data storage, simplified for MVP.
Only essential tables: kontoj (accounts), dosierujoj (folders), mesagoj (messages).
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

_IDX_MESAGOJ_KONTO = "CREATE INDEX IF NOT EXISTS idx_mesagoj_konto ON mesagoj(konto_id);"
_IDX_MESAGOJ_DOSIERUJO = "CREATE INDEX IF NOT EXISTS idx_mesagoj_dosierujo ON mesagoj(dosierujo_id);"
_IDX_MESAGOJ_IMAP_UID = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_mesagoj_imap_uid
    ON mesagoj(konto_id, dosierujo_id, imap_uid)
    WHERE imap_uid IS NOT NULL;
"""
_IDX_MESAGOJ_DATO = "CREATE INDEX IF NOT EXISTS idx_mesagoj_dato ON mesagoj(ricevita_je);"

_SCHEMA_STATEMENTS: list[str] = [
    _CREATE_KONTOJ,
    _CREATE_DOSIERUJOJ,
    _CREATE_MESAGOJ,
    _IDX_MESAGOJ_KONTO,
    _IDX_MESAGOJ_DOSIERUJO,
    _IDX_MESAGOJ_IMAP_UID,
    _IDX_MESAGOJ_DATO,
]

# ── Database path ───────────────────────────────────────────────────────────


def _email_db_path() -> Path:
    return data_dir() / "email.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    """Get the email database connection with schema initialized."""
    resolved = Path(path) if path else _email_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STATEMENTS:
        db.execute(stmt)
    return db
