# AGENTS-calendar.md — Calendar Module Agent Instructions

## Summary

Calendar, todo (tasks), and journal module, forked from [A-organizi](../../A-organizi). Provides CalDAV sync, event management, todo/task management with formula-based priority, journal entries, and shared labels.

## Purpose and Expected Behavior

`src/lighterbird/calendar/` provides:

- **`caldav/`** — CalDAV client, sync queue, push/pull, password management
- **`events/`** — Event CRUD, recurrence (RRULE), ICS import/export
- **`todo.py`** — Task CRUD with formula-based priority engine and labels
- **`journal.py`** — Journal entry CRUD (multiple entries per day)
- **`labels/`** — Shared label management (tags shared between todo and journal)
- **`utils/`** — ICS parsing, markdown rendering, undo support

## Constraints and Invariants

- **CalDAV sync is queued** — operations are enqueued, processed by a background worker thread
- **Passwords in system keyring** — no password column in the calendars table
- **Event dedup uses content matching** — title + start + end (not ETags, which aren't available from all providers)
- **Priority is a formula string** — e.g., `"min(20+2*D,70)"` — evaluated at query time based on days remaining (inherited from A-organizi/autish)
- **Labels are shared** between todo and journal via a junction table (`todoj_etikedo`, `taglibro_etikedo`)
- **Multiple journal entries per day** — UUID PK, not date PK

## Input/Output Expectations

- `pull_events(calendar_uuid)` fetches all remote events via CalDAV REPORT
- `push_event(event_uuid)` PUTs to remote CalDAV server (auto-called on create/update/delete)
- `search_todos(query)` searches by title (normalized text matching)
- `search_events(start, end)` queries events within a date range
- `queue_sync(calendar_uuid, operation, payload)` enqueues a sync job

## Documentation Reference

- [A-organizi AGENTS.md](../../A-organizi/AGENTS.md) — full architecture, DB schema, sync design
- [A-organizi sync.py](../../A-organizi/src/A_organizi/utils/sync.py) — CalDAV sync engine source
- [A-organizi okazajo_rrule.py](../../A-organizi/src/A_organizi/cli/okazajo_rrule.py) — RRULE shorthand expander

## Domain-Specific Rules for Agents

1. **Fork the service layer, not the CLI.** A-organizi's Typer CLI code stays behind. The service layer (`KalendaroService`, `TodoService`, `TaglibroService`) is what to carry forward.
2. **Rename to English.** `kalendaro` → `calendar`, `okazajo` → `events`, `taglibro` → `journal`, `etikedoj` → `labels`.
3. **DB column names stay Esperanto** for compatibility with existing user data (e.g., `komenco`, `fino`, `titolo`, `prioritato`).
4. **Simplify the sync worker.** A-organizi's `sync_worker()` is a thread with polling loop (`time.sleep(5)`). Consider using an async pattern or a simpler polling model in lighterbird.
5. **Strip duplicates from A-core.** A-organizi has its own `keyring.py` copy — use `core/keyring.py` instead.
6. **Keep the RRULE shorthand system** — it's a genuine UX improvement over raw RFC 5545 syntax.
7. **Adapt error reporting** — A-organizi uses `error()`, `info()` from A.core. Use Python logging or structured exceptions.
