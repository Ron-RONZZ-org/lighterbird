"""Todo database schema and initialization."""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_TASKOJ = """
CREATE TABLE IF NOT EXISTS taskoj (
    uuid            TEXT PRIMARY KEY,
    titolo          TEXT NOT NULL,
    priskribo       TEXT NOT NULL DEFAULT '',
    prioritato      INTEGER NOT NULL DEFAULT 5,
    stato           TEXT NOT NULL DEFAULT 'pending',
    limdato         TEXT,
    kreita_je       TEXT NOT NULL,
    modifita_je     TEXT NOT NULL
);
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_TASKOJ,
    "CREATE INDEX IF NOT EXISTS idx_taskoj_stato ON taskoj(stato);",
]


def _todo_db_path() -> Path:
    return data_dir() / "todo.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    resolved = Path(path) if path else _todo_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    return db
