"""Journal database schema and initialization."""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_TAGLIBRO = """
CREATE TABLE IF NOT EXISTS taglibro (
    uuid            TEXT PRIMARY KEY,
    titolo          TEXT NOT NULL DEFAULT '',
    teksto          TEXT NOT NULL DEFAULT '',
    dato            TEXT NOT NULL,
    kreita_je       TEXT NOT NULL,
    modifita_je     TEXT NOT NULL
);
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_TAGLIBRO,
    "CREATE INDEX IF NOT EXISTS idx_taglibro_dato ON taglibro(dato);",
]


def _journal_db_path() -> Path:
    return data_dir() / "journal.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    resolved = Path(path) if path else _journal_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    return db
