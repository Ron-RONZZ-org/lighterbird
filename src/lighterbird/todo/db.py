"""Todo database schema and initialization.

Schema includes tasks table with formula-based priority,
labels table, todo_labels junction table, plus
subtask hierarchy (parent_uuid), dependencies, file attachments,
and templates.
"""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir

_CREATE_TASKS = """
CREATE TABLE IF NOT EXISTS tasks (
    uuid            TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    priority        TEXT NOT NULL DEFAULT '5',
    status          TEXT NOT NULL DEFAULT 'pending',
    due_date        TEXT,
    parent_uuid     TEXT REFERENCES tasks(uuid) ON DELETE SET NULL,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    template_uuid   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

_CREATE_TODO_DEPENDENCIES = """
CREATE TABLE IF NOT EXISTS todo_dependencies (
    task_uuid     TEXT NOT NULL REFERENCES tasks(uuid) ON DELETE CASCADE,
    depends_on    TEXT NOT NULL REFERENCES tasks(uuid) ON DELETE CASCADE,
    type          TEXT NOT NULL DEFAULT 'blocks'
                  CHECK(type IN ('blocks', 'blocked_by')),
    created_at    TEXT NOT NULL,
    PRIMARY KEY (task_uuid, depends_on),
    CHECK (task_uuid != depends_on)
);
"""

_CREATE_ATTACHMENTS = """
CREATE TABLE IF NOT EXISTS attachments (
    uuid            TEXT PRIMARY KEY,
    todo_uuid       TEXT NOT NULL REFERENCES tasks(uuid) ON DELETE CASCADE,
    original_name   TEXT NOT NULL,
    original_path   TEXT NOT NULL DEFAULT '',
    cache_path      TEXT NOT NULL DEFAULT '',
    mime_type       TEXT NOT NULL DEFAULT '',
    size            INTEGER NOT NULL DEFAULT 0,
    md5_checksum    TEXT NOT NULL DEFAULT '',
    last_synced_at  TEXT,
    sync_status     TEXT NOT NULL DEFAULT 'pending'
                    CHECK(sync_status IN ('pending','synced','pending_update','error')),
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
"""

_CREATE_TEMPLATES = """
CREATE TABLE IF NOT EXISTS templates (
    uuid              TEXT PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE,
    title_placeholder TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
"""

_CREATE_TEMPLATE_FIELDS = """
CREATE TABLE IF NOT EXISTS template_fields (
    uuid            TEXT PRIMARY KEY,
    template_uuid   TEXT NOT NULL REFERENCES templates(uuid) ON DELETE CASCADE,
    field_name      TEXT NOT NULL,
    field_type      TEXT NOT NULL CHECK(field_type IN ('text','file','markdown')),
    is_required     INTEGER NOT NULL DEFAULT 0,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    UNIQUE (template_uuid, field_name)
);
"""

_MIGRATE_TASKS_PARENT = """
ALTER TABLE tasks ADD COLUMN parent_uuid TEXT REFERENCES tasks(uuid) ON DELETE SET NULL;
"""

_MIGRATE_TASKS_SORT = """
ALTER TABLE tasks ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0;
"""

_MIGRATE_TASKS_TEMPLATE = """
ALTER TABLE tasks ADD COLUMN template_uuid TEXT;
"""

_SCHEMA_STMTS: list[str] = [
    _CREATE_TASKS,
    _CREATE_TODO_DEPENDENCIES,
    _CREATE_ATTACHMENTS,
    _CREATE_TEMPLATES,
    _CREATE_TEMPLATE_FIELDS,
    "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);",
    "CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_todo_dependencies_task ON todo_dependencies(task_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_todo_dependencies_dep ON todo_dependencies(depends_on);",
    "CREATE INDEX IF NOT EXISTS idx_attachments_todo ON attachments(todo_uuid);",
    "CREATE INDEX IF NOT EXISTS idx_template_fields_template ON template_fields(template_uuid);",
]

_MIGRATIONS: list[str] = [
    _MIGRATE_TASKS_PARENT,
    _MIGRATE_TASKS_SORT,
    _MIGRATE_TASKS_TEMPLATE,
]


def _todo_db_path() -> Path:
    return data_dir() / "todo.db"


def get_db(path: Path | str | None = None) -> LighterbirdDB:
    """Get the todo database connection with schema initialized."""
    resolved = Path(path) if path else _todo_db_path()
    db = LighterbirdDB(resolved)
    for stmt in _SCHEMA_STMTS:
        db.execute(stmt)
    for stmt in _MIGRATIONS:
        try:
            db.execute(stmt)
        except Exception:
            pass
    return db
