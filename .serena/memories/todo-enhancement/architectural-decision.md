# Todo Enhancement — Architectural Decision

## Summary
Enhancing the flat todo system with subtasks, dependencies, file attachments, and templates.

## Status
**Implemented** — PR #47 merged to main on 2026-06-28

## Key Decisions
1. **parent_uuid** (self-referencing FK) for subtask hierarchy
2. **todoj_dependoj** junction table for dependencies (separate from parent/child)
3. **Tree view extends existing list-tab pattern** — flatten tree, add indentation + expand/collapse. `createSelectionManager` works unmodified on flattened UUIDs.
4. **Reparent on delete** (not cascade) via `_post_delete` hook
5. **Templates inside todo domain** — not a separate module
6. **File cache in cache_dir(), not BLOBs** — metadata table in todo.db
7. **`!sync --todo-attachments`** flag on existing sync command (no new subcommand)
8. **Backend returns flat+metadata** for tree (not recursive JSON)

## Phasing
- **Phase 1**: Core hierarchy (3-5 days)
- **Phase 2**: Template system (2-3 days)
- **Phase 3**: File attachments (3-4 days, deferrable)

## References
- Issue: #46
- AGENTS-root.md
- AGENTS-calendar.md
- AGENTS-core.md
