# AGENTS-calendar.md — Calendar Module Agent Instructions

## Summary

Calendar and events module, forked from [A-organizi](../../A-organizi). Provides CalDAV sync, event management with recurrence (RRULE), and ICS import/export.

## Purpose and Expected Behavior

`src/lighterbird/calendar/` provides:

- **`caldav.py`** — CalDAV client, sync queue, push/pull, password management
- **`service.py`** — Event CRUD, recurrence (RRULE), ICS import/export
- **`services/`** — Domain service layer (`CalendarService`)

## Constraints and Invariants

- **CalDAV sync is queued** — operations are enqueued, processed by a background worker thread
- **Passwords in system keyring** — no password column in the calendars table
- **Event dedup uses content matching** — title + start + end (not ETags, which aren't available from all providers)
- **Event dedup uses UUID-based matching** — stable identifiers from CalDAV where available, fallback to content matching

## Input/Output Expectations

- `pull_events(calendar_uuid)` fetches all remote events via CalDAV REPORT
- `push_event(event_uuid)` PUTs to remote CalDAV server (auto-called on create/update/delete)
- `search_events(start, end)` queries events within a date range
- `queue_sync(calendar_uuid, operation, payload)` enqueues a sync job

## Documentation Reference

- [A-organizi AGENTS.md](../../A-organizi/AGENTS.md) — full architecture, DB schema, sync design
- [A-organizi sync.py](../../A-organizi/src/A_organizi/utils/sync.py) — CalDAV sync engine source

## Domain-Specific Rules for Agents

1. **Fork the service layer, not the CLI.** A-organizi's Typer CLI code stays behind. The service layer (`CalendarService`) is what to carry forward.
2. **Rename to English.** `kalendaro` → `calendar`, `okazajo` → `events`.
3. **DB column names use English** — migrated from Esperanto in v0.3.0 (e.g., `start`, `end`, `title`).
4. **Todo and journal extracted to own modules.** Task management now lives in `src/lighterbird/todo/`, journal entries in `src/lighterbird/journal/`. The calendar module focuses on events only.
5. **Simplify the sync worker.** A-organizi's `sync_worker()` is a thread with polling loop (`time.sleep(5)`). lighterbird uses a simpler trigger-based sync model.
6. **Strip duplicates from A-core.** A-organizi has its own `keyring.py` copy — use `core/keyring.py` instead.
7. **Keep the RRULE shorthand system** — it's a genuine UX improvement over raw RFC 5545 syntax.
8. **Adapt error reporting** — A-organizi uses `error()`, `info()` from A.core. Use Python logging or structured exceptions.
