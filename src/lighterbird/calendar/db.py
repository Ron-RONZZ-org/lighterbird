"""Calendar database schema and initialization.

Schema includes: calendars, events.
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_CALENDARS = """
CREATE TABLE IF NOT EXISTS calendars (
    uuid        TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    username    TEXT NOT NULL DEFAULT '',
    remote      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

_CREATE_EVENTS = """
CREATE TABLE IF NOT EXISTS events (
    uuid           TEXT PRIMARY KEY,
    calendar_uuid  TEXT NOT NULL,
    title          TEXT NOT NULL DEFAULT '',
    start          TEXT NOT NULL,
    end            TEXT NOT NULL,
    category       TEXT NOT NULL DEFAULT '',
    location       TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    remote_href    TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
"""

_CREATE_STMTS: list[str] = [
    _CREATE_CALENDARS,
    _CREATE_EVENTS,
    "CREATE INDEX IF NOT EXISTS idx_events_calendar ON events(calendar_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_events_start ON events(start);",
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
