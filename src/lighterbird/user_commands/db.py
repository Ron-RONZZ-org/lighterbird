"""User commands database schema and initialization.

Follows the per-module SQLite file pattern from email/, contacts/, etc.
"""

from __future__ import annotations

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_DB_PATH = data_dir() / "user_commands.db"

_SCHEMA = {
    "saved_commands": """
CREATE TABLE IF NOT EXISTS saved_commands (
    uuid              TEXT PRIMARY KEY,
    alias             TEXT NOT NULL UNIQUE,
    command_template  TEXT NOT NULL,
    hint              TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    modified_at       TEXT NOT NULL
);
""",
}

_db: LighterbirdDB | None = None


def get_db() -> LighterbirdDB:
    """Get the singleton user_commands database."""
    global _db
    if _db is None:
        _db = LighterbirdDB(_DB_PATH)
        _db.init_schema(_SCHEMA)
    return _db


def reset_db() -> None:
    """Reset the DB singleton (for testing)."""
    global _db
    if _db is not None:
        _db.close()
        _db = None
