"""Journal database schema and initialization.

Schema includes journal (journal entries) table, labels table,
and journal_labels junction table.
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_JOURNAL = """
CREATE TABLE IF NOT EXISTS journal (
    uuid            TEXT PRIMARY KEY,
    title           TEXT NOT NULL DEFAULT '',
    text            TEXT NOT NULL DEFAULT '',
    date            TEXT NOT NULL DEFAULT (date('now')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_JOURNAL,
    "CREATE INDEX IF NOT EXISTS idx_journal_date ON journal(date);",
]


def _journal_db_path() -> Path:
    return data_dir() / "journal.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    resolved = Path(path) if path else _journal_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    return db
