"""Todo database schema and initialization.

Schema includes taskoj table with formula-based priority (TEXT),
etikedoj (labels) table, todoj_etikedo junction table, plus
subtask hierarchy (parent_uuid), dependencies, file attachments,
and templates.
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
    parent_uuid     TEXT REFERENCES taskoj(uuid) ON DELETE SET NULL,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    shablono_uuid   TEXT,
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

_CREATE_TODOJ_DEPENDOJ = """
CREATE TABLE IF NOT EXISTS todoj_dependoj (
    task_uuid     TEXT NOT NULL REFERENCES taskoj(uuid) ON DELETE CASCADE,
    dependanta_je TEXT NOT NULL REFERENCES taskoj(uuid) ON DELETE CASCADE,
    type          TEXT NOT NULL DEFAULT 'blocks'
                  CHECK(type IN ('blocks', 'blocked_by')),
    kreita_je     TEXT NOT NULL,
    PRIMARY KEY (task_uuid, dependanta_je),
    CHECK (task_uuid != dependanta_je)
);
"""

_CREATE_ALDONAJXOJ = """
CREATE TABLE IF NOT EXISTS aldonajxoj (
    uuid            TEXT PRIMARY KEY,
    todo_uuid       TEXT NOT NULL REFERENCES taskoj(uuid) ON DELETE CASCADE,
    origina_nomo    TEXT NOT NULL,
    origina_vojo    TEXT NOT NULL DEFAULT '',
    kasko_vojo      TEXT NOT NULL DEFAULT '',
    dosier_peco     TEXT NOT NULL DEFAULT '',
    grandeco        INTEGER NOT NULL DEFAULT 0,
    md5_cheksumo    TEXT NOT NULL DEFAULT '',
    last_sync_je    TEXT,
    sync_stato      TEXT NOT NULL DEFAULT 'pending'
                    CHECK(sync_stato IN ('pending','synced','pending_update','error')),
    kreita_je       TEXT NOT NULL,
    modifita_je     TEXT NOT NULL
);
"""

_CREATE_SHABLONOJ = """
CREATE TABLE IF NOT EXISTS shablonoj (
    uuid              TEXT PRIMARY KEY,
    nomo              TEXT NOT NULL UNIQUE,
    title_placeholder TEXT NOT NULL DEFAULT '',
    kreita_je         TEXT NOT NULL,
    modifita_je       TEXT NOT NULL
);
"""

_CREATE_SHABLONAJ_KAMPOJ = """
CREATE TABLE IF NOT EXISTS shablonaj_kampoj (
    uuid            TEXT PRIMARY KEY,
    shablono_uuid   TEXT NOT NULL REFERENCES shablonoj(uuid) ON DELETE CASCADE,
    kampo_nomo      TEXT NOT NULL,
    kampo_tipo      TEXT NOT NULL CHECK(kampo_tipo IN ('text','file','markdown')),
    estas_deviga    INTEGER NOT NULL DEFAULT 0,
    ordo            INTEGER NOT NULL DEFAULT 0,
    UNIQUE (shablono_uuid, kampo_nomo)
);
"""

_MIGRATE_TASKOJ_PARENT = """
ALTER TABLE taskoj ADD COLUMN parent_uuid TEXT REFERENCES taskoj(uuid) ON DELETE SET NULL;
"""

_MIGRATE_TASKOJ_SORT = """
ALTER TABLE taskoj ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0;
"""

_MIGRATE_TASKOJ_SHABLONO = """
ALTER TABLE taskoj ADD COLUMN shablono_uuid TEXT;
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_TASKOJ,
    _CREATE_ETIKEDOJ,
    _CREATE_TODOJ_ETIKEDO,
    _CREATE_TODOJ_DEPENDOJ,
    _CREATE_ALDONAJXOJ,
    _CREATE_SHABLONOJ,
    _CREATE_SHABLONAJ_KAMPOJ,
    "CREATE INDEX IF NOT EXISTS idx_taskoj_stato ON taskoj(stato);",
    "CREATE INDEX IF NOT EXISTS idx_taskoj_parent ON taskoj(parent_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_todoj_etikedo_todo ON todoj_etikedo(todo_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_todoj_etikedo_etikedo ON todoj_etikedo(etikedo_teksto);",
    "CREATE INDEX IF NOT EXISTS idx_todoj_dependoj_task ON todoj_dependoj(task_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_todoj_dependoj_dep ON todoj_dependoj(dependanta_je);",
    "CREATE INDEX IF NOT EXISTS idx_aldonajxoj_todo ON aldonajxoj(todo_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_shablonaj_kampoj_shablono ON shablonaj_kampoj(shablono_uuid);",
]

_MIGRATIONS: list[str] = [
    _MIGRATE_TASKOJ_PARENT,
    _MIGRATE_TASKOJ_SORT,
    _MIGRATE_TASKOJ_SHABLONO,
]


def _todo_db_path() -> Path:
    return data_dir() / "todo.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    """Get the todo database connection with schema initialized."""
    resolved = Path(path) if path else _todo_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    # Run migrations (safe to re-run — ALTER TABLE ADD COLUMN is no-op if exists)
    for stmt in _MIGRATIONS:
        try:
            db.execute(stmt)
        except Exception:
            pass  # Column already exists
    return db
