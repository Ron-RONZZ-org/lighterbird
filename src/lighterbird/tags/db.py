"""Tags database schema and initialization.

Schema
------
tags
    name        TEXT PRIMARY KEY COLLATE NOCASE
    color       TEXT NOT NULL DEFAULT ''
    created_at  TEXT NOT NULL
    updated_at  TEXT NOT NULL

taggings
    tag_name    TEXT NOT NULL REFERENCES tags(name) ON DELETE CASCADE
    domain      TEXT NOT NULL         -- 'todo', 'journal', 'letter', etc.
    item_uuid   TEXT NOT NULL
    created_at  TEXT NOT NULL
    PRIMARY KEY (tag_name, domain, item_uuid)

Usage::

    from lighterbird.tags.db import get_db
    db = get_db()
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_TAGS = """
CREATE TABLE IF NOT EXISTS tags (
    name        TEXT PRIMARY KEY COLLATE NOCASE,
    color       TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""

_CREATE_TAGGINGS = """
CREATE TABLE IF NOT EXISTS taggings (
    tag_name    TEXT NOT NULL REFERENCES tags(name) ON DELETE CASCADE,
    domain      TEXT NOT NULL,
    item_uuid   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (tag_name, domain, item_uuid)
);
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_TAGS,
    _CREATE_TAGGINGS,
    "CREATE INDEX IF NOT EXISTS idx_taggings_item ON taggings(domain, item_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_taggings_tag ON taggings(tag_name);",
]


def _tags_db_path() -> Path:
    return data_dir() / "tags.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    """Get the tags database connection with schema initialized."""
    resolved = Path(path) if path else _tags_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    return db
