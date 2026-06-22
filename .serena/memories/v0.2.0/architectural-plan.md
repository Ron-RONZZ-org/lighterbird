# lighterbird v0.2.0 — Architectural Plan

## Decision Log
- **Implementation status:** COMPLETE (2026-06-22)
- All features implemented and verified. 103/103 tests pass.
- See issue [#4](https://github.com/Ron-RONZZ-org/lighterbird/issues/4) for details.

- **Date:** 2026-06-22
- **Decision by:** User + architect agent consultation
- **GitHub Issue:** [#4](https://github.com/Ron-RONZZ-org/lighterbird/issues/4)

## Verdict

Proposal approved. All items align with AGENTS.md project goals and conventions.

## Changes vs. Original Proposal

- **OAuth2** deferred to v0.3.0 (password/app-password sufficient, complex provider-specific quirks)
- **i18n** deferred to v0.3.0 (mechanical, touches every file, English-only acceptable)
- **Database merge** rejected for v0.2.0 (per-module SQLite files are fine)
- **Full RRULE recurrence** excluded for v0.2.0 (complex, local events stay simple)

## In Scope for v0.2.0

1. Contacts, Todo, Journal enhancement (basic CRUD exists, needs FTS5, labels, VCF, formula priority)
2. CalDAV push + background sync worker (`core/worker.py`, `server/tasks.py`)
3. Attachments, HTML email, signatures (`core/storage.py`, schema changes, SMTP refactor)
4. Sieve filters / spam (`email/filters/` submodule)
5. LLM integration (`core/ai.py`, `core/providers.py`, streaming SSE)

## New Infrastructure Modules

- `src/lighterbird/core/worker.py` — Background worker: thread-safe queue, single consumer, FastAPI lifespan
- `src/lighterbird/core/storage.py` — AttachmentStore: filesystem-backed, `{data_dir}/attachments/{msg_uuid}/`
- `src/lighterbird/server/tasks.py` — Orchestration layer, enqueue_*() functions
- `src/lighterbird/core/ai.py` — ProviderConfig, stateless provider factory
- `src/lighterbird/core/providers.py` — OpenAICompatibleProvider + OllamaProvider with streaming

## Key Architectural Decisions

- Worker pattern: single thread per worker type (avoids SQLite contention), daemon threads + stop event for shutdown
- LLM streaming: SSE (StreamingResponse) initially, WebSocket kept as alternative
- Attachments: metadata-only in DB, blobs on filesystem via AttachmentStore
- CalDAV push: HTTP PUT/DELETE with If-Match, enqueued via worker
- Labels: per-module etikedoj + junction tables (todo_db has its own, journal_db has its own)
- OAuth schema readiness: add `auth_type` column to kontoj as text-only placeholder

## Risks to Monitor

- Worker thread silent death: catch-all error handler in _run() loop
- Disk space from attachments: configurable max size, orphan cleanup on message delete
- CalDAV ETag conflict: clear error reporting, re-fetch + merge or abort

## Implementation Order

1. Infrastructure (parallel): core/worker.py, core/storage.py
2. Module enhancements (parallel): contacts, todo, journal, Sieve
3. Email enhancements: SMTP refactor, IMAP parser, schema (depends on storage)
4. Calendar push: caldav.py push methods, worker wiring (depends on worker)
5. LLM: ai.py + providers.py, streaming route, command generation
