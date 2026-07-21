# AGENTS-email.md — Email Module Agent Instructions

## Summary

Email module, forked from [A-lien](../../A-lien). Provides IMAP sync, SMTP send, account management, Sieve filter management, spam blocking, and email signatures.

## Purpose and Expected Behavior

`src/lighterbird/email/` provides:

- **`imap/`** — IMAP sync engine: client, message parser, concurrent sync, UID-based dedup
- **`smtp.py`** — SMTP send with attachments, HTML body, signatures, priority headers
- **`accounts/`** — Email account CRUD + keyring password management
- **`filters/`** — Sieve filter CRUD + ManageSieve sync, SpamManager (block senders/domains + Sieve rule generation)
- **`signatures/`** — Per-account email signature management
- **`undo.py`** — Deferred email operation with undo support.  Thread-safe in-memory registry
  for pending email operations (trash, hard-delete, spam, fraud) that can be reverted within a
  5-second window via ``UndoRegistry``.  After the timer expires, IMAP backlog entries are
  enqueued and the operation becomes permanent.  Used by ``POST /email/messages/batch-delete``,
  ``POST /email/messages/batch-delete-hard``, and ``POST /email/spam/report`` when called with
  ``delay_seconds > 0``.  The undo endpoint is ``POST /api/v1/email/actions/undo/{operation_id}``.

## Constraints and Invariants

- **Passwords in system keyring only** — no `pasvorto` column in the accounts table
- **Messages use IMAP UID for dedup** — `imap_uid` is the stable remote identifier
- **HTML body is stored alongside plaintext** — both are preserved for the frontend to decide rendering
- **Attachments are metadata in DB + blobs on disk** — file blobs are stored via ``AttachmentStore`` (keyed by message UUID + content ID). The ``email_attachments`` table tracks metadata.
- **Inline images (``cid:``) are stored as attachments** — MIME parts with ``Content-ID`` headers are captured as attachments even without explicit filename/name. The frontend rewrites ``cid:`` URLs in HTML bodies to the CID resolution API route.
- **export_eml reconstructs full MIME** — ``MessageService.export_eml()`` builds a proper multipart/alternative (or multipart/mixed) with html_body and attachments, not a plain-text-only reconstruction.
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

Key rule: **hard-delete (batch-delete-hard via GUI, clear-trash, REST `POST /api/v1/email/messages/batch-delete`) deletes the local DB row immediately** and enqueues an `'expunge'` backlog entry. The IMAP EXPUNGE happens asynchronously, giving instant UX — same contract as soft delete. `hard_delete_message()` returns a dict with `count`, `queued`, and `errors` — no longer raises on IMAP failure. The CLI `!email delete` has been removed — use GUI REST endpoints for all delete operations.

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

### Recent rename: ``!email spam`` → ``!email block``

The ``!email spam`` command tree has been renamed to ``!email block`` (issue #245):

- ``!email block list`` → ``block-list`` tab type (``BlockedSendersListTab.svelte``)
- ``!email block add <sender> [--note TEXT]`` → status + highlight, interactive form fallback
- **No CLI ``remove``/``modify``** — edit/delete are GUI-only via the list tab (REST API)
- REST API: ``GET /api/v1/email/blocks``, ``PATCH /api/v1/email/blocks/{uuid}``, ``DELETE /api/v1/email/blocks/{uuid}``
- ``SpamManager`` now supports ``note`` field (reason for blocking)
- ``spam_blocks`` table has ``note TEXT NOT NULL DEFAULT ''`` column (added directly, pre-release — no migration needed)
- ``!email signature list`` → ``signature-list`` tab type (``SignatureListTab.svelte``)
- ``!email signature default`` → interactive form with account email dropdown + signature autocomplete
- ``PATCH /api/v1/email/signatures/{uuid}`` and ``DELETE /api/v1/email/signatures/{uuid}`` for GUI edit/delete

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
15. **View subcommands** — ``!email list draft`` and ``!email draft list`` both open the ``EmailListTab`` filtered to the Drafts folder (with ``_isDraftView``). ``!email list trash`` opens the trash view. Other view subcommands: ``inbox``, ``all``, ``outbox``, ``archive``, ``junk``, ``spam``. The legacy ``!email draft`` (bare) and ``!email trash`` commands have been removed — use the view subcommands instead.
16. **``!email draft new``** — Opens the compose form for drafting a new email. All params are optional; any provided args pre-populate the form. The form auto-saves drafts as the user types via the frontend's draft REST API. ``!email draft recall`` has been removed — use ``GET /api/v1/drafts/<uuid>`` via the GUI for draft recall.
17. **Spam detection architecture** — three-tier system:
    - **Bayesian classifier** (``spam_detect.py``): Chi-squared token combination (SpamBayes algorithm). Ships ``spam_tokens.json`` pre-baked seed table. Per-user training in ``spam_user_tokens`` table. Threshold: >0.9 spam, <0.15 ham.
    - **Phishing detector** (``phishing.py``): Structural heuristics + feed-based URL lookup (OpenPhish/PhishTank/PhishStats — same feeds as SpamAssassin's Phishing plugin). Does NOT train the Bayesian model. Includes user watchlist from Fraudulent marks.
    - **Three-action GUI** in ``EmailHeaders.svelte``: ``[+ Contact] [🗑 Block] [⚠ Spam]``. Block → Sieve ``reject``. Spam → Bayesian train + move to \Spam folder. Fraudulent → watchlist + hard-delete.
    - **DB additions**: ``spam_user_tokens``, ``phishing_feeds``, ``phishing_domains``, ``spam_feedback`` tables. New columns on ``messages``: ``is_spam``, ``spam_score``, ``spam_reported``, ``ham_reported``, ``phishing_detected``.
    - **CLI**: ``!email spam stats`` only. Reporting is GUI/LLM-only (UUIDs are not CLI-friendly).
18. **Pre-sync backlog drain contract** — ``EmailService.sync_account()`` drains all pending backlog entries (expunge, trash, flag sync) for the account BEFORE acquiring the IMAP sync lock. This prevents re-import of hard-deleted messages and ensures flag state consistency. The previously separate post-sync ``process_sync_backlog()`` has been removed — the pre-sync drain subsumes it. Any entries enqueued during sync (e.g. user flag toggles during the sync window) will be picked up by the next sync cycle or background worker. Best-effort contract: if the BacklogService lock is busy, sync proceeds without draining.

18. **Enhanced local search (``!email search --header``)** — ``MessageService.search_messages()`` now searches **all** message fields when a free-text ``query`` is provided:
    - Fields: ``subject``, ``from_addr``, ``to_recipients``, ``cc_recipients``, ``body``
    - Results are ordered by **relevance score**: subject (weight 3) > sender (2) > recipients (1) > body (0.5)
    - Each result includes a ``matched_in`` list of field names for frontend match badges
    - Cursor-based pagination falls back to time-based sort (relevance ordering is incompatible with cursor format)
    - The ``--participant`` flag (search From/To/CC) now works on the local SQL path (previously only IMAP remote)
    - Body preview in search results uses **match-centered snippets** rather than simple prefix truncation
19. **``_extract_match_snippet(body, query, context=100)``** — Module-level helper in ``messages.py`` that extracts a match-centered window from body text. Replaces the first-N-chars truncation when a search query is present.

### Phase 6: IMAP IDLE Integration (Issue #240)

Phase 5 built ``IMAPIdleThread`` and ``IMAPIdleManager`` in ``idle.py``, but they were never wired into the server lifecycle. Phase 6 (this phase) connects them:

**Backend wiring:**
- ``idle.py``: Fixed the IDLE loop to use proper RFC 2177 (``IDLE`` → block on server push via ``select.select()`` → ``DONE``), replacing the broken NOOP-polling implementation. Added ``get_imap_idle_manager()`` module-level singleton.
- ``server/sync_state.py``: New ``SyncStateManager`` singleton — thread-safe per-account sync state tracking (``startup-syncing``, ``idle``, ``syncing``, ``error``, ``disabled``). Tracks startup completion across all accounts and fires ``on_startup_complete`` callbacks.
- ``server/tasks.py``: ``EmailSyncWorker.start()`` now enqueues a ``startup-sync`` job. ``_do_startup_sync()`` runs initial full sync for all accounts, then starts IDLE threads. Added ``start_idle_for_new_account()`` / ``stop_idle_for_account()`` / ``stop_all_idle()`` for lifecycle management. Added 5-minute periodic polling fallback for servers without IDLE support (``_do_poll_check()``).
- ``server/app.py``: ``init_sync_state_manager()`` in lifespan startup; ``stop_all_idle()`` in shutdown.
- Account CRUD routes: Create → start IDLE; Update (password/IMAP change) → restart IDLE; Delete → stop IDLE.

**Frontend:**
- ``syncStore.svelte.js``: New reactive store polling ``GET /api/v1/email/sync/status`` every 10s. Exposes ``syncState`` (``startupComplete``, ``accounts``, ``summary``, ``statusClass``).
- ``SyncStatusBar.svelte``: Thin non-blocking status bar showing sync/IDLE health (green ✓ for IDLE, amber ⟳ for syncing, red ⚠ for errors). Clickable to trigger manual sync.
- ``EmailListTab.svelte``: Removed blocking ``SyncOverlay`` on mount. Now loads data from local DB immediately and shows\ ``SyncStatusBar`` instead. Manual sync (Ctrl+R) still shows ``SyncOverlay``.
- ``EmailFolderTab.svelte``: Same pattern — removed blocking sync on mount.

**Key constraint:** No new dependencies (stdlib ``imaplib``, ``select``, ``threading`` only).
