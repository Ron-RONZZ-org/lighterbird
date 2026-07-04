# AGENTS-journal.md — Journal Module Agent Instructions

## Summary

Journal entry management module for lighterbird. Provides CRUD for daily journal entries, markdown export/import with YAML frontmatter, and label management.

## Purpose and Expected Behavior

`src/lighterbird/journal/` provides:

- **`db.py`** — `journal` table schema with label junction table
- **`services/journal.py`** — `JournalService(CRUDService)`: create, read, update, delete, search, markdown export/import, label management

## Constraints and Invariants

- **Multiple entries per day** — UUID primary key (not date-based), allowing multiple journal entries per day
- **Body stored as markdown** — the canonical storage format for journal entries
- **Labels via junction table** — `journal_labels` for many-to-many label assignment
- **Markdown export includes YAML frontmatter** — metadata (uuid, created_at, labels) serialized as YAML between `---` delimiters
- **Markdown import parses YAML frontmatter** — `wrap()` / `unwrap()` in `core/yaml_frontmatter.py`
- **FTS5 search** — full-text search on title and body text

## Input/Output Expectations

- `!journal list` returns `{"type": "journal-list", ...}` — rendered by `JournalListTab`
- `!journal write` returns `{"type": "status", ...}` with the new entry UUID
- `!journal export md <uuid>` returns a markdown string with YAML frontmatter
- `!journal import md <path>` returns import count
- `search(query, tags, limit)` searches via FTS5 MATCH with optional tag filter

## Documentation Reference

- [A-organizi AGENTS.md](../../A-organizi/AGENTS.md) — original source for journal functionality
- Core module (`core/`) — shared YAML frontmatter utilities in `core/yaml_frontmatter.py`
- Todo module (`todo/`) — follows the same CRUDService + markdown export/import pattern

## Domain-Specific Rules for Agents

1. **Extracted from calendar module.** Journal was originally part of A-organizi's calendar module. In lighterbird it lives in its own `journal/` module.
2. **Markdown is the interchange format.** Both export and import use markdown with YAML frontmatter. The body content is stored as markdown in the DB.
3. **Labels are shared only conceptually.** The journal module has its own `journal_labels` junction table. There is no global label store — labels are per-module.
4. **Body path storage.** The `body_path` column stores the path to a file on disk containing the full body content, keeping the DB row lightweight.
5. **Keep the daily-entry flexibility.** Unlike a traditional diary (one entry per day), lighterbird allows multiple entries on the same date.
