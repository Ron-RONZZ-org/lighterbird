"""Contacts database schema and initialization.

Schema includes contacts table with FTS5 full-text search.
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_CONTACTS = """
CREATE TABLE IF NOT EXISTS contacts (
    uuid            TEXT PRIMARY KEY,
    given_name      TEXT NOT NULL DEFAULT '',
    family_name     TEXT NOT NULL DEFAULT '',
    full_name       TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    phone           TEXT NOT NULL DEFAULT '',
    organization    TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    category        TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

_CREATE_CONTACTS_FTS5 = """
CREATE VIRTUAL TABLE IF NOT EXISTS contacts_fts USING fts5(
    given_name, family_name, full_name, email, organization, notes,
    content='contacts',
    content_rowid='rowid'
);
"""

_CREATE_FTS_TRIGGER_INSERT = """
CREATE TRIGGER IF NOT EXISTS contacts_ai AFTER INSERT ON contacts BEGIN
    INSERT INTO contacts_fts(rowid, given_name, family_name, full_name, email, organization, notes)
    VALUES (new.rowid, new.given_name, new.family_name, new.full_name, new.email, new.organization, new.notes);
END;
"""

_CREATE_FTS_TRIGGER_DELETE = """
CREATE TRIGGER IF NOT EXISTS contacts_ad AFTER DELETE ON contacts BEGIN
    INSERT INTO contacts_fts(contacts_fts, rowid, given_name, family_name, full_name, email, organization, notes)
    VALUES ('delete', old.rowid, old.given_name, old.family_name, old.full_name, old.email, old.organization, old.notes);
END;
"""

_CREATE_FTS_TRIGGER_UPDATE = """
CREATE TRIGGER IF NOT EXISTS contacts_au AFTER UPDATE ON contacts BEGIN
    INSERT INTO contacts_fts(contacts_fts, rowid, given_name, family_name, full_name, email, organization, notes)
    VALUES ('delete', old.rowid, old.given_name, old.family_name, old.full_name, old.email, old.organization, old.notes);
    INSERT INTO contacts_fts(rowid, given_name, family_name, full_name, email, organization, notes)
    VALUES (new.rowid, new.given_name, new.family_name, new.full_name, new.email, new.organization, new.notes);
END;
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_CONTACTS,
    _CREATE_CONTACTS_FTS5,
    _CREATE_FTS_TRIGGER_INSERT,
    _CREATE_FTS_TRIGGER_DELETE,
    _CREATE_FTS_TRIGGER_UPDATE,
    "CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);",
]


def _contacts_db_path() -> Path:
    return data_dir() / "contacts.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    resolved = Path(path) if path else _contacts_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    return db
