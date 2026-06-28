"""Todo database schema and initialization.

Schema includes taskoj table with formula-based priority (TEXT),
etikedoj (labels) table, and todog_etikedo junction table.
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_TASKOJ = """
CREATE TABLE IF NOT EXISTS taskoj (
    uuid            TEXT PRIMARY KEY,
    titolo          TEXT NOT NULL,
    priskribo       TEXT NOT NULL DEFAULT '',
    prioritato      TEXT NOT NULL DEFAULT '5',
    stato           TEXT NOT NULL DEFAULT 'pending',
    limdato         TEXT,
    kreita_je       TEXT NOT NULL,
    modifita_je     TEXT NOT NULL
);
"""

_CREATE_ETIKEDOJ = """
CREATE TABLE IF NOT EXISTS etikedoj (
    teksto      TEXT PRIMARY KEY COLLATE NOCASE,
    koloro      TEXT NOT NULL DEFAULT '',
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_TODOJ_ETIKEDO = """
CREATE TABLE IF NOT EXISTS todoj_etikedo (
    todo_uuid      TEXT NOT NULL REFERENCES taskoj(uuid) ON DELETE CASCADE,
    etikedo_teksto TEXT NOT NULL REFERENCES etikedoj(teksto) ON DELETE CASCADE,
    PRIMARY KEY (todo_uuid, etikedo_teksto)
);
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_TASKOJ,
    _CREATE_ETIKEDOJ,
    _CREATE_TODOJ_ETIKEDO,
    "CREATE INDEX IF NOT EXISTS idx_taskoj_stato ON taskoj(stato);",
    "CREATE INDEX IF NOT EXISTS idx_todoj_etikedo_todo ON todoj_etikedo(todo_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_todoj_etikedo_etikedo ON todoj_etikedo(etikedo_teksto);",
]


def _todo_db_path() -> Path:
    return data_dir() / "todo.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    resolved = Path(path) if path else _todo_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    return db
