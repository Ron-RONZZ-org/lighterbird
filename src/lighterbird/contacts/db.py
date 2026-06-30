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
    middle_names    TEXT NOT NULL DEFAULT '',
    family_name     TEXT NOT NULL DEFAULT '',
    full_name       TEXT NOT NULL DEFAULT '',
    emails          TEXT NOT NULL DEFAULT '[]',
    phones          TEXT NOT NULL DEFAULT '[]',
    organization    TEXT NOT NULL DEFAULT '',
    position        TEXT NOT NULL DEFAULT '',
    address         TEXT NOT NULL DEFAULT '',
    post_code       TEXT NOT NULL DEFAULT '',
    date_of_birth   TEXT NOT NULL DEFAULT '',
    place_of_birth  TEXT NOT NULL DEFAULT '',
    notes           TEXT NOT NULL DEFAULT '',
    category        TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

_CREATE_CONTACTS_FTS5 = """
CREATE VIRTUAL TABLE IF NOT EXISTS contacts_fts USING fts5(
    given_name, middle_names, family_name, full_name, emails, phones,
    organization, address, notes,
    content='contacts',
    content_rowid='rowid'
);
"""

_CREATE_FTS_TRIGGER_INSERT = """
CREATE TRIGGER IF NOT EXISTS contacts_ai AFTER INSERT ON contacts BEGIN
    INSERT INTO contacts_fts(rowid, given_name, middle_names, family_name, full_name, emails, phones, organization, address, notes)
    VALUES (new.rowid, new.given_name, new.middle_names, new.family_name, new.full_name, new.emails, new.phones, new.organization, new.address, new.notes);
END;
"""

_CREATE_FTS_TRIGGER_DELETE = """
CREATE TRIGGER IF NOT EXISTS contacts_ad AFTER DELETE ON contacts BEGIN
    INSERT INTO contacts_fts(contacts_fts, rowid, given_name, middle_names, family_name, full_name, emails, phones, organization, address, notes)
    VALUES ('delete', old.rowid, old.given_name, old.middle_names, old.family_name, old.full_name, old.emails, old.phones, old.organization, old.address, old.notes);
END;
"""

_CREATE_FTS_TRIGGER_UPDATE = """
CREATE TRIGGER IF NOT EXISTS contacts_au AFTER UPDATE ON contacts BEGIN
    INSERT INTO contacts_fts(contacts_fts, rowid, given_name, middle_names, family_name, full_name, emails, phones, organization, address, notes)
    VALUES ('delete', old.rowid, old.given_name, old.middle_names, old.family_name, old.full_name, old.emails, old.phones, old.organization, old.address, old.notes);
    INSERT INTO contacts_fts(rowid, given_name, middle_names, family_name, full_name, emails, phones, organization, address, notes)
    VALUES (new.rowid, new.given_name, new.middle_names, new.family_name, new.full_name, new.emails, new.phones, new.organization, new.address, new.notes);
END;
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_CONTACTS,
    _CREATE_CONTACTS_FTS5,
    _CREATE_FTS_TRIGGER_INSERT,
    _CREATE_FTS_TRIGGER_DELETE,
    _CREATE_FTS_TRIGGER_UPDATE,
]


def _contacts_db_path() -> Path:
    return data_dir() / "contacts.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    resolved = Path(path) if path else _contacts_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    return db
