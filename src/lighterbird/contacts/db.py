"""Contacts database schema and initialization.

Schema includes kontaktoj table with FTS5 full-text search.
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_KONTAKTOJ = """
CREATE TABLE IF NOT EXISTS kontaktoj (
    uuid            TEXT PRIMARY KEY,
    nomo            TEXT NOT NULL DEFAULT '',
    familia_nomo    TEXT NOT NULL DEFAULT '',
    plena_nomo      TEXT NOT NULL DEFAULT '',
    retposto        TEXT NOT NULL DEFAULT '',
    telefonnumero   TEXT NOT NULL DEFAULT '',
    organizo        TEXT NOT NULL DEFAULT '',
    notoj           TEXT NOT NULL DEFAULT '',
    kategorio       TEXT NOT NULL DEFAULT '',
    kreita_je       TEXT NOT NULL,
    modifita_je     TEXT NOT NULL
);
"""

_CREATE_KONTAKTOJ_FTS5 = """
CREATE VIRTUAL TABLE IF NOT EXISTS kontaktoj_fts USING fts5(
    nomo, familia_nomo, plena_nomo, retposto, organizo, notoj,
    content='kontaktoj',
    content_rowid='rowid'
);
"""

_CREATE_FTS_TRIGGER_INSERT = """
CREATE TRIGGER IF NOT EXISTS kontaktoj_ai AFTER INSERT ON kontaktoj BEGIN
    INSERT INTO kontaktoj_fts(rowid, nomo, familia_nomo, plena_nomo, retposto, organizo, notoj)
    VALUES (new.rowid, new.nomo, new.familia_nomo, new.plena_nomo, new.retposto, new.organizo, new.notoj);
END;
"""

_CREATE_FTS_TRIGGER_DELETE = """
CREATE TRIGGER IF NOT EXISTS kontaktoj_ad AFTER DELETE ON kontaktoj BEGIN
    INSERT INTO kontaktoj_fts(kontaktoj_fts, rowid, nomo, familia_nomo, plena_nomo, retposto, organizo, notoj)
    VALUES ('delete', old.rowid, old.nomo, old.familia_nomo, old.plena_nomo, old.retposto, old.organizo, old.notoj);
END;
"""

_CREATE_FTS_TRIGGER_UPDATE = """
CREATE TRIGGER IF NOT EXISTS kontaktoj_au AFTER UPDATE ON kontaktoj BEGIN
    INSERT INTO kontaktoj_fts(kontaktoj_fts, rowid, nomo, familia_nomo, plena_nomo, retposto, organizo, notoj)
    VALUES ('delete', old.rowid, old.nomo, old.familia_nomo, old.plena_nomo, old.retposto, old.organizo, old.notoj);
    INSERT INTO kontaktoj_fts(rowid, nomo, familia_nomo, plena_nomo, retposto, organizo, notoj)
    VALUES (new.rowid, new.nomo, new.familia_nomo, new.plena_nomo, new.retposto, new.organizo, new.notoj);
END;
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_KONTAKTOJ,
    _CREATE_KONTAKTOJ_FTS5,
    _CREATE_FTS_TRIGGER_INSERT,
    _CREATE_FTS_TRIGGER_DELETE,
    _CREATE_FTS_TRIGGER_UPDATE,
    "CREATE INDEX IF NOT EXISTS idx_kontaktoj_retposto ON kontaktoj(retposto);",
]


def _contacts_db_path() -> Path:
    return data_dir() / "contacts.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    resolved = Path(path) if path else _contacts_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    return db
