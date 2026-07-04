# AGENTS-todo.md — Todo Module Agent Instructions

## Summary

Task/todo management module for lighterbird. Provides CRUD for tasks with formula-based priority, label tagging, subtask hierarchy, dependency tracking, file attachments, markdown export/import with YAML frontmatter, and task templates.

## Purpose and Expected Behavior

`src/lighterbird/todo/` provides:

- **`db.py`** — `tasks` table schema with subtask self-reference, dependencies, labels junction table, attachments
- **`services/todo.py`** — `TodoService(CRUDService)`: create, read, update, delete, search, tree building, formula priority, markdown I/O, templates

## Constraints and Invariants

- **Priority is a formula string** — e.g., `"min(20+2*D,70)"` where `D` = days remaining. Evaluated at query time by `core/priority.py`.
- **Subtasks via self-referencing FK** — `parent_uuid` column references `tasks.uuid`
- **Dependencies as junction table** — `task_dependencies` for blocking/predecessor relationships
- **Labels via junction table** — `task_labels` for many-to-many label assignment
- **Body stored as markdown** — canonical storage format for task descriptions
- **Markdown export includes YAML frontmatter** — metadata (uuid, priority, status, tags, created_at) serialized as YAML
- **Markdown import supports subtask expansion** — nested bullet lists become subtask hierarchy
- **Templates** — pre-defined task structures with `$1`, `$2` placeholder substitution
- **File attachments** — binary files stored on disk, metadata in DB (path, filename, size, mime_type)

## Input/Output Expectations

- `!todo list` returns `{"type": "todo-list", ...}` — rendered by `TodoListTab`
- `!todo tree` returns hierarchical todo list (parent + subtasks)
- `!todo add` returns `{"type": "status", ...}` with the new task UUID
- `!todo export md <uuid>` returns a markdown string with YAML frontmatter
- `!todo import md <path>` returns import count
- `search(query, status, tags, limit, sort)` searches with optional filters
- `tree(status, tags)` returns nested structure with children in `children` key

## Documentation Reference

- [A-organizi AGENTS.md](../../A-organizi/AGENTS.md) — original source for todo functionality
- Core module (`core/`) — priority formula evaluator in `core/priority.py`, YAML frontmatter in `core/yaml_frontmatter.py`
- Journal module (`journal/`) — follows the same CRUDService + markdown export/import pattern

## Domain-Specific Rules for Agents

1. **Extracted from calendar module.** Todo was originally part of A-organizi's calendar module. In lighterbird it lives in its own `todo/` module.
2. **Priority formula engine is shared.** The `eval_safe()` / `validate_safe()` functions live in `core/priority.py` and must be kept secure (no arbitrary code execution).
3. **Tree view is a backend concern.** The `todo tree` command builds the parent-child tree in the service layer using recursive queries. The frontend `TodoListTab` renders flat or tree based on a `mode` parameter.
4. **Markdown is the interchange format.** Both export and import use markdown with YAML frontmatter. Subtask hierarchy is preserved via bullet nesting.
5. **Label scope is per-module.** The todo module has its own `task_labels` junction table, separate from journal labels.
6. **Template system.** Tasks can be created from templates stored in the `task_templates` table. Placeholders (`$1`, `$2`, etc.) are replaced at creation time.
