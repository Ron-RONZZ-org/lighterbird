"""Profiles database schema and initialization.

Each profile represents a user identity (e.g. "work", "home", "personal")
with structured contact, demographic, and custom fields stored as JSON.
"""

from __future__ import annotations

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_DB_PATH = data_dir() / "profiles.db"

_SCHEMA = {
    "user_profiles": """
CREATE TABLE IF NOT EXISTS user_profiles (
    uuid            TEXT PRIMARY KEY,
    profile_name    TEXT NOT NULL,           -- e.g. "work", "home", "personal"
    given_name      TEXT NOT NULL DEFAULT '',
    middle_names    TEXT NOT NULL DEFAULT '',
    family_name     TEXT NOT NULL DEFAULT '',
    full_name       TEXT NOT NULL DEFAULT '', -- computed
    date_of_birth   TEXT NOT NULL DEFAULT '',  -- YYYY-MM-DD
    place_of_birth  TEXT NOT NULL DEFAULT '',
    emails          TEXT NOT NULL DEFAULT '[]', -- JSON: [{"tag":"work","value":"a@b.com"},...]
    phones          TEXT NOT NULL DEFAULT '[]', -- JSON: [{"tag":"mobile","value":"+123"},...]
    address         TEXT NOT NULL DEFAULT '',
    post_code       TEXT NOT NULL DEFAULT '',
    organization    TEXT NOT NULL DEFAULT '',
    position        TEXT NOT NULL DEFAULT '',
    custom_fields   TEXT NOT NULL DEFAULT '{}', -- JSON: {"key1":"value1","key2":"value2"}
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
""",
}

_db: LighterbirdDB | None = None


def get_db() -> LighterbirdDB:
    """Get the singleton profiles database."""
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
