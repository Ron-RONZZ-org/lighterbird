# AGENTS-email.md — Email Module Agent Instructions

## Summary

Email module, forked from [A-lien](../../A-lien). Provides IMAP sync, SMTP send, account management, Sieve filter management, spam blocking, and email signatures.

## Purpose and Expected Behavior

`src/lighterbird/email/` provides:

- **`imap/`** — IMAP sync engine: client, message parser, concurrent sync, UID-based dedup
- **`smtp.py`** — SMTP send with attachments, HTML body, signatures, priority headers
- **`accounts/`** — Email account CRUD + keyring password management
- **`filters/`** — Sieve filter CRUD + ManageSieve sync
- **`spam.py`** — Spam block management + Sieve rule generation
- **`signatures/`** — Per-account email signature management

## Constraints and Invariants

- **Passwords in system keyring only** — no `pasvorto` column in the accounts table
- **Messages use IMAP UID for dedup** — `imap_uid` is the stable remote identifier
- **HTML body is stored alongside plaintext** — both are preserved for the frontend to decide rendering
- **Attachments are metadata-only in DB** — file blobs are extracted on demand via IMAP FETCH
- **Flag changes sync back to IMAP server via backlog queue** — read/star/trash state is pushed via backlog
- **Concurrent sync uses ThreadPoolExecutor** — one thread per account folder
- **CONDSTORE (RFC 4551) for flag pull** — server-side flag changes (starred on phone) are pulled on sync
- **UIDVALIDITY tracked per folder** — UID reassignment detected and handled gracefully
- **Connection pool per account** — reused across backlog processing for efficiency

## Input/Output Expectations

- `sync_all()` returns `dict[str, SyncResult]` keyed by account UUID
- `search_messages(filters)` uses IMAP SEARCH (network) — local FTS5 may be added later
- `send_email(...)` stores a copy of the sent message in the local DB

## Documentation Reference

- [A-lien AGENTS.md](../../A-lien/AGENTS.md) — full service architecture, DB schema, CLI tree
- [A-lien retposto_sync.py](../../A-lien/src/A_lien/service/retposto_sync.py) — sync mixin source
- [A-lien imap/client.py](../../A-lien/src/A_lien/imap/client.py) — IMAPClient source

## IMAP Sync Engine Overhaul (Phase 0-5)

### Architecture

The IMAP sync engine was overhauled in phases addressing 10 identified gaps:

| Phase | Component | Description |
|-------|-----------|-------------|
| 0 | Schema + Services | Added modseq/uidvalidity/special_use columns, dead_letters table. Extracted BacklogService, DeadLetterService, FlagSyncService from msg_ops.py. |
| 1 | UIDVALIDITY | `IMAPClient.select_folder_ex()` parses SELECT response for UIDVALIDITY and HIGHESTMODSEQ. On UIDVALIDITY mismatch, local messages for that folder are invalidated and re-fetched. |
| 2 | Folder Mapping | `FolderMapper` resolves canonical folder names (Trash, Sent, Junk) to server-localized names using SPECIAL-USE flags from IMAP LIST. Falls back to known alias lists. |
| 3 | CONDSTORE/QRESYNC | `detect_capabilities()` parses server capabilities at connect time. `FlagPuller` uses `FETCH (UID FLAGS MODSEQ) (CHANGEDSINCE N)` to pull server-side flag changes. Merge semantics: local backlog wins over server state. |
| 4 | Connection Pool | `IMAPConnectionPool` maintains per-account connections with idle timeout. Reused by backlog processing to avoid per-operation connection overhead. |
| 5 | IMAP IDLE | `IMAPIdleThread` runs a per-account IDLE loop with reconnection. `IMAPIdleManager` manages thread lifecycle. Callbacks trigger incremental sync on EXISTS/FLAGS events. |

### Sync Backlog (IMAP Flag Sync)

Flag changes (read/delete) are synced back to the IMAP server via a backlog queue:

1. **`BacklogService.enqueue()`** — Queues a pending flag change with INSERT OR REPLACE
2. **`_sync_backlog` table** — Stores pending flag changes with account, folder, IMAP UID, desired flag state, and retry count
3. **`BacklogService.process_all()`** — Acquires threading lock, processes entries per account, connects via pool, sends STORE ±FLAGS.SILENT or UID MOVE. Escalates to dead-letter after `MAX_RETRIES` (10).
4. **`DeadLetterService`** — Stores entries that exhausted retries for manual review. Supports list, clear, and retry-back-to-backlog operations.
5. **`FlagSyncService`** — Orchestrates push (backlog drain) and pull (CONDSTORE flag sync)

### Locking

Backlog processing uses `threading.Lock` with a 5-second timeout. If the lock is held by another thread (e.g., manual sync triggering backlog drain while background worker is processing), the second caller returns 0 gracefully.

### Dead-Letter Limits

Entries exceeding `MAX_RETRIES` (default: 10) are automatically moved to the `_dead_letters` table. They can be retried via `DeadLetterService.retry_entry()` or cleared via `DeadLetterService.clear()`.

## Domain-Specific Rules for Agents

1. **Fork the service layer, not the CLI.** A-lien's CLI code (Typer commands) stays behind. The services are what matter — they expose the `EmailService` API.
2. **Rename to English.** `retposto` → `email`, `mesagoj` → `messages`, `dosierujoj` → `folders`, `retposto_konto` → `accounts`. Update all variable names and comments accordingly.
3. **DB column names use English** — migrated from Esperanto in v0.3.0 (e.g., `subject`, `received_at`, `account_email`).
4. **Simplify the mixin hierarchy.** A-lien uses 7+ mixins composed into a single class. lighterbird uses `EmailService` + `AccountService` with simpler delegation.
5. **Contacts extracted to own module.** Contacts CRUD and VCF import/export now live in `src/lighterbird/contacts/`. The email module communicates with contacts only via `contact_uuid` references.
6. **Strip keyring.py** — lighterbird already has one in `core/keyring.py`.
7. **OAuth2 must be added** for modern email providers (Gmail, Outlook). Design the auth interface now even if only password auth is implemented initially.
8. **Adapt error reporting.** A-lien uses `error()`, `info()` from A.core. lighterbird should use Python logging or raise structured exceptions for the server layer to handle.
9. **New services added in Phase 0:** `BacklogService`, `DeadLetterService`, `FlagSyncService` are available via `EmailService.msg_ops.backlog`, `EmailService.msg_ops.dead_letter`, and `EmailService.msg_ops.flag_sync`.
10. **File sizes:** `msg_ops.py` reduced from 455→221 lines after extraction. New files: `backlog.py` (377), `dead_letter.py` (169), `flag_sync.py` (89), `capabilities.py` (76), `folder_mapper.py` (141), `flag_pull.py` (338), `connpool.py` (220), `idle.py` (315). All under 500-line limit.
