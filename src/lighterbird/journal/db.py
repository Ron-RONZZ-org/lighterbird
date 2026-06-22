"""Journal database schema and initialization.

Schema includes taglibro (journal entries) table, etikedoj (labels) table,
and taglibro_etikedo junction table.
"""

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

_CREATE_ETIKEDOJ = """
CREATE TABLE IF NOT EXISTS etikedoj (
    uuid        TEXT PRIMARY KEY,
    teksto      TEXT NOT NULL UNIQUE,
    koloro      TEXT NOT NULL DEFAULT '',
    kreita_je   TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_TAGLIBRO_ETIKEDO = """
CREATE TABLE IF NOT EXISTS taglibro_etikedo (
    taglibro_uuid TEXT NOT NULL REFERENCES taglibro(uuid) ON DELETE CASCADE,
    etikedo_uuid  TEXT NOT NULL REFERENCES etikedoj(uuid) ON DELETE CASCADE,
    PRIMARY KEY (taglibro_uuid, etikedo_uuid)
);
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_TAGLIBRO,
    _CREATE_ETIKEDOJ,
    _CREATE_TAGLIBRO_ETIKEDO,
    "CREATE INDEX IF NOT EXISTS idx_taglibro_dato ON taglibro(dato);",
    "CREATE INDEX IF NOT EXISTS idx_taglibro_etikedo_entry ON taglibro_etikedo(taglibro_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_taglibro_etikedo_label ON taglibro_etikedo(etikedo_uuid);",
]


def _journal_db_path() -> Path:
    return data_dir() / "journal.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    resolved = Path(path) if path else _journal_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    return db
