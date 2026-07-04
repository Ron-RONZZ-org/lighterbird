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

_CREATE_SYNC_QUEUE = """
CREATE TABLE IF NOT EXISTS calendar_sync_queue (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_uuid   TEXT NOT NULL,
    event_uuid      TEXT NOT NULL,
    operation       TEXT NOT NULL CHECK(operation IN ('push', 'delete')),
    remote_href     TEXT,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'running', 'completed', 'failed')),
    error           TEXT NOT NULL DEFAULT '',
    retries         INTEGER NOT NULL DEFAULT 0,
    max_retries     INTEGER NOT NULL DEFAULT 5,
    next_attempt    TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

_MIGRATE_SYNC_QUEUE_RETRIES = """
ALTER TABLE calendar_sync_queue ADD COLUMN retries INTEGER NOT NULL DEFAULT 0;
"""
_MIGRATE_SYNC_QUEUE_MAX_RETRIES = """
ALTER TABLE calendar_sync_queue ADD COLUMN max_retries INTEGER NOT NULL DEFAULT 5;
"""
_MIGRATE_SYNC_QUEUE_NEXT_ATTEMPT = """
ALTER TABLE calendar_sync_queue ADD COLUMN next_attempt TEXT;
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
    _CREATE_SYNC_QUEUE,
    _MIGRATE_SYNC_QUEUE_RETRIES,
    _MIGRATE_SYNC_QUEUE_MAX_RETRIES,
    _MIGRATE_SYNC_QUEUE_NEXT_ATTEMPT,
    "CREATE INDEX IF NOT EXISTS idx_events_calendar ON events(calendar_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_events_start ON events(start);",
    "CREATE INDEX IF NOT EXISTS idx_sync_queue_status ON calendar_sync_queue(status);",
    "CREATE INDEX IF NOT EXISTS idx_sync_queue_calendar ON calendar_sync_queue(calendar_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_sync_queue_retry ON calendar_sync_queue(status, next_attempt);",
]


def _calendar_db_path() -> Path:
    return data_dir() / "calendar.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    """Get the calendar database connection with schema initialized."""
    from sqlite3 import OperationalError

    resolved = Path(path) if path else _calendar_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _CREATE_STMTS:
        try:
            db.execute(stmt)
        except OperationalError:
            if not stmt.strip().upper().startswith("ALTER"):
                raise
    return db
