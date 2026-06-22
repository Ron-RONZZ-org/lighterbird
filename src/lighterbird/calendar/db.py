"""Calendar database schema and initialization.

Forked from A-organizi's data storage, simplified for MVP.
Only essential tables: kalendaroj (calendars), eventoj (events).
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_KALENDAROJ = """
CREATE TABLE IF NOT EXISTS kalendaroj (
    uuid        TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    username    TEXT NOT NULL DEFAULT '',
    remote      INTEGER NOT NULL DEFAULT 1,
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_EVENTOJ = """
CREATE TABLE IF NOT EXISTS eventoj (
    uuid           TEXT PRIMARY KEY,
    kalendaro_uuid TEXT NOT NULL,
    titolo         TEXT NOT NULL DEFAULT '',
    komenco        TEXT NOT NULL,
    fino           TEXT NOT NULL,
    kategorio      TEXT NOT NULL DEFAULT '',
    loko           TEXT NOT NULL DEFAULT '',
    priskribo      TEXT NOT NULL DEFAULT '',
    remote_href    TEXT,
    kreita_je      TEXT NOT NULL,
    modifita_je    TEXT NOT NULL
);
"""

_CREATE_STMTS: list[str] = [
    _CREATE_KALENDAROJ,
    _CREATE_EVENTOJ,
    "CREATE INDEX IF NOT EXISTS idx_eventoj_kalendaro ON eventoj(kalendaro_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_eventoj_komenco ON eventoj(komenco);",
]


def _calendar_db_path() -> Path:
    return data_dir() / "calendar.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    """Get the calendar database connection with schema initialized."""
    resolved = Path(path) if path else _calendar_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _CREATE_STMTS:
        db.execute(stmt)
    return db
