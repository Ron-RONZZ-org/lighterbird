"""Contacts database schema and initialization."""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_KONTAKTOJ = """
CREATE TABLE IF NOT EXISTS kontaktoj (
    uuid            TEXT PRIMARY KEY,
    nomo            TEXT NOT NULL DEFAULT '',
    retposto        TEXT NOT NULL DEFAULT '',
    telefonnumero   TEXT NOT NULL DEFAULT '',
    organizo        TEXT NOT NULL DEFAULT '',
    notoj           TEXT NOT NULL DEFAULT '',
    kreita_je       TEXT NOT NULL,
    modifita_je     TEXT NOT NULL
);
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_KONTAKTOJ,
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
