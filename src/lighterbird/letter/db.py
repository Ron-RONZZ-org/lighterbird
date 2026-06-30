"""Letters database schema and initialization."""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_LETTERS = """
CREATE TABLE IF NOT EXISTS letters (
    uuid              TEXT PRIMARY KEY,
    direction         TEXT NOT NULL CHECK(direction IN ('sent','received')),
    object            TEXT NOT NULL DEFAULT '',
    body_path         TEXT NOT NULL DEFAULT '',
    body_format       TEXT NOT NULL DEFAULT 'html',
    sender_profile    TEXT,
    sender_manual     TEXT NOT NULL DEFAULT '',
    recipient_contact TEXT,
    recipient_manual  TEXT NOT NULL DEFAULT '',
    respond_to_uuid   TEXT REFERENCES letters(uuid),
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
"""

_CREATE_LETTERS_RESPOND_INDEX = """
CREATE INDEX IF NOT EXISTS idx_letters_respond_to ON letters(respond_to_uuid);
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_LETTERS,
    _CREATE_LETTERS_RESPOND_INDEX,
]


def _letter_db_path() -> Path:
    return data_dir() / "letters.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    resolved = Path(path) if path else _letter_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    return db
