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

### Sync Backlog (IMAP Operations)

Backend IMAP operations (flag sync, trash move, permanent deletion) are deferred via a backlog queue:

1. **`BacklogService.enqueue()`** — Queues a pending operation with INSERT OR REPLACE
2. **`_sync_backlog` table** — Stores pending operations with account, folder, IMAP UID, desired flag state, retry count, and **operation type**:
   - `'sync'` — flag sync (\\Seen, \\Deleted) — the original/default
   - `'trash'` — move message to IMAP Trash folder (UID MOVE / COPY+EXPUNGE)
   - `'expunge'` — permanent deletion from IMAP (STORE +FLAGS.SILENT (\\Deleted) + EXPUNGE). No local DB update (calling code already deleted the row).
3. **`BacklogService.process_all()`** — Acquires threading lock, processes entries per account, connects via pool, sends STORE ±FLAGS.SILENT, UID MOVE, or EXPUNGE depending on operation type. Escalates to dead-letter after `MAX_RETRIES` (10).
4. **`DeadLetterService`** — Stores entries that exhausted retries for manual review. Supports list, clear, and retry-back-to-backlog operations. The `operation` column is preserved through dead-letter cycles.
5. **`FlagSyncService`** — Orchestrates push (backlog drain) and pull (CONDSTORE flag sync)

Key rule: **hard-delete (`!email delete --hard`, batch-delete-hard, clear-trash) deletes the local DB row immediately** and enqueues an `'expunge'` backlog entry. The IMAP EXPUNGE happens asynchronously, giving instant UX — same contract as soft delete. `hard_delete_message()` returns a dict with `count`, `queued`, and `errors` — no longer raises on IMAP failure.

### Pre-Sync Backlog Drain

Before `EmailService.sync_account()` acquires the per-account IMAP lock for an
IMAP sync scan, it drains ALL pending backlog entries for that account first.
This ensures all local operations (hard-delete, soft-delete, flag changes) are
reflected on the IMAP server before the scan, preventing:

- **Re-import of hard-deleted messages**: The expunge backlog entry removes the
  UID from the server before the sync's UID SEARCH scans for it.
- **Trash folder consistency**: The trash backlog entry moves the message to
  the IMAP Trash folder before the sync discovers it there.
- **Flag freshness**: Locally set read/starred flags are pushed to the server
  before CONDSTORE pull during sync.

The pre-sync drain runs **before** the sync's own IMAP lock acquisition. The
`BacklogService` acquires its own per-account IMAP lock internally, so the two
operations serialize correctly — the sync waits for the backlog's IMAP
connection to finish before starting its own.

The previously separate post-sync `process_sync_backlog()` call has been
removed — the pre-sync drain subsumes it. Backlog entries enqueued during sync
(e.g. user flag toggles) will be picked up by the next sync cycle or background
worker.

**Best-effort contract**: If the BacklogService lock is busy (another thread
processing backlog), `process_all()` returns 0 gracefully and the sync proceeds
without draining. The backlog entries remain for the next cycle.

### Locking (Two Levels)

Backlog processing uses two levels of locking for thread safety:

1. **BacklogService lock** (`threading.Lock`, 5s timeout) — Serializes backlog table processing. If the lock is held by another thread (e.g., manual sync triggering backlog drain while background worker is processing), the second caller returns 0 gracefully.

2. **Per-account IMAP lock** (`threading.Lock` per account email, 30s timeout) — Prevents concurrent IMAP connections for the same account. Multiple paths can open IMAP connections independently (background worker `_do_sync`, `_do_process_trash`, user-initiated `!email sync`, `POST /api/v1/sync/start`). Without coordination, these connections can race on the same IMAP folder (one thread scanning UIDs while another EXPUNGEs), causing missed or duplicated messages.

   Lock acquisition flow:
   - `EmailService.sync_account()` — pre-sync backlog drain runs first (BacklogService acquires its own IMAP lock internally), THEN sync's IMAP lock is acquired for the scan
   - `BacklogService._process_account()` — acquires before IMAP connect for backlog processing, releases in `finally`
   
   Lock ordering is strictly sequential (never nested): the pre-sync drain's IMAP lock is released before the sync scan's IMAP lock is acquired. If the backlog drain cannot acquire its IMAP lock within the timeout, it returns 0 gracefully and the sync proceeds without draining.

   If the sync scan's IMAP lock cannot be acquired within the 30s timeout, the caller logs a warning and gracefully returns with an error message (backlog entries remain for next cycle).

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
11. **Signature modify accepts name (or UUID).** ``!email signature modify`` takes signature name (or UUID) as the first positional argument. The handler resolves by name first, falling back to UUID (backward compatible). When invoked without modification flags (``--name``, ``--text``, ``--format``), the handler returns a ``form-required`` response with existing data pre-filled.
12. **Send path uses shared render_utils for body conversion.** ``msg_compose.py:send_email()`` now uses ``convert_to_html()`` from ``server.render_utils`` instead of ``mistune.html()`` for markdown→HTML conversion. This ensures the send path produces the same HTML as the preview endpoint (``POST /api/v1/email/preview``). The ``compose_email_html()`` utility is the single source of truth for email composition, used by both preview and send.
13. **IMAP Draft Sync (Phase 6).** Email drafts are synced bidirectionally with the IMAP DRAFTS folder:
    - **Local → IMAP** (``save_draft_to_imap()``): When a user saves a draft via Ctrl+S in the compose form, a minimal RFC 2822 message is built and appended to the IMAP DRAFTS folder via ``IMAPConnectionPool`` + per-account IMAP lock. The ``APPENDUID`` response is parsed to track the IMAP UID in the ``email_draft_uid_map`` table, so subsequent saves avoid SEARCH HEADER.
    - **IMAP → Local** (``_sync_imap_drafts_to_local()``): Called as Phase 2b of ``sync_account()``. Uses UIDNEXT-based incremental scan of the Drafts folder. New drafts are imported into ``_drafts.json`` via ``save_draft()``.
    - **Deletion** (``DELETE /api/v1/drafts/<uuid>``): For email drafts with an IMAP presence, an ``expunge`` backlog entry is enqueued to remove the draft from the IMAP server.
    - **Folder resolution**: ``FolderMapper.resolve_drafts()`` resolves localized Drafts folder names using SPECIAL-USE ``\\Drafts`` or alias lists (``[Gmail]/Drafts``, ``Entwürfe``, ``Brouillons``, etc.).
14. **``email_draft_uid_map`` SQLite table** — Tracks the correlation between local draft UUIDs and IMAP UIDs. Primary key is ``(account_email, folder_name, draft_uuid)``. Used to avoid SEARCH HEADER on subsequent saves and to enable IMAP→local inverse sync.
15. **``!email draft`` opens Drafts folder pane** — ``!email draft`` opens the ``EmailListTab`` filtered to the Drafts folder (with ``_isDraftView``). ``!email draft recall <uuid>`` recalls a saved composition draft.
16. **``!email trash list`` simplified to ``!email trash``** — The ``list`` sub-command is removed for consistency. ``!email trash`` opens the trash view directly.
17. **Pre-sync backlog drain contract** — ``EmailService.sync_account()`` drains all pending backlog entries (expunge, trash, flag sync) for the account BEFORE acquiring the IMAP sync lock. This prevents re-import of hard-deleted messages and ensures flag state consistency. The previously separate post-sync ``process_sync_backlog()`` has been removed — the pre-sync drain subsumes it. Any entries enqueued during sync (e.g. user flag toggles during the sync window) will be picked up by the next sync cycle or background worker. Best-effort contract: if the BacklogService lock is busy, sync proceeds without draining.
