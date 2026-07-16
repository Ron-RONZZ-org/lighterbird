# RAG Writing Samples for Cowrite — Design (2026-07-07)

Issue: https://github.com/Ron-RONZZ-org/lighterbird/issues/136

## Status
Architecturally approved (@architect consulted). Phase 1 design ready for implementation.

## Key Decisions
- **Embedding strategy**: SQLite FTS5 (phase 1, zero deps) → optional sqlite-vec (phase 3)
- **Storage**: Per-domain DB (email.db, journal.db, todo.db) with `writing_samples` table + FTS5 index
- **Registration timing**: Send-time (after SMTP success) for email; save-time for journal/todo
- **Opt-out UX**: Checkbox in compose form (default on) + global default in `~/.config/lighterbird/settings.json`
- **Domain model**: Generic from day one — schema is identical across domains
- **Retrieval hook**: `gather_context()` in `server/cowrite/context.py` — already stubbed for this
- **Embedding computation**: Server-side (Python), colocated with LLM provider

## Data Model
```sql
CREATE TABLE writing_samples (
    uuid            TEXT PRIMARY KEY,
    source_uuid     TEXT NOT NULL,
    source_domain   TEXT NOT NULL,
    title           TEXT,
    body            TEXT NOT NULL,
    body_format     TEXT DEFAULT 'plain',
    language        TEXT,
    word_count      INTEGER,
    registered_at   TEXT NOT NULL
);

CREATE VIRTUAL TABLE writing_samples_fts USING fts5(
    uuid UNINDEXED, title, body,
    content='writing_samples',
    content_rowid='rowid'
);
```

## Implementation Phases
1. **Phase 1**: Email only — schema, registration hook, FTS5 retrieval, GUI checkbox, settings toggle
2. **Phase 2**: Journal + todo — identical pattern across domains
3. **Phase 3**: Vector upgrade — embed() on provider, BLOB column, cosine-similarity

No editing has started yet.
