# AGENTS-email.md — Email Module Agent Instructions

## Summary

Email and contacts module, forked from [A-lien](../../A-lien). Provides IMAP sync, SMTP send, contact management (VCF), account management, Sieve filter management, and spam blocking.

## Purpose and Expected Behavior

`src/lighterbird/email/` provides:

- **`imap/`** — IMAP sync engine: client, message parser, concurrent sync, UID-based dedup
- **`smtp.py`** — SMTP send with attachments, HTML body, signatures, priority headers
- **`contacts/`** — Contact CRUD, VCF import/export, FTS5 search, categories, dedup
- **`accounts/`** — Email account CRUD + keyring password management
- **`filters/`** — Sieve filter CRUD + ManageSieve sync
- **`spam.py`** — Spam block management + Sieve rule generation

## Constraints and Invariants

- **Passwords in system keyring only** — no `pasvorto` column in the accounts table
- **Contacts indexed by FTS5** on name, email, organization, notes
- **Messages use IMAP UID for dedup** — `imap_uid` is the stable remote identifier
- **HTML body is stored alongside plaintext** — both are preserved for the frontend to decide rendering
- **Attachments are metadata-only in DB** — file blobs are extracted on demand via IMAP FETCH
- **Flag changes sync back to IMAP server** — read/star/trash state is pushed via a backlog queue
- **Concurrent sync uses ThreadPoolExecutor** — one thread per account folder

## Input/Output Expectations

- `sync_all()` returns `dict[str, SyncResult]` keyed by account UUID
- `search_messages(filters)` uses IMAP SEARCH (network) — local FTS5 may be added later
- `send_email(...)` stores a copy of the sent message in the local DB
- `import_vcf(path)` returns count of imported contacts

## Documentation Reference

- [A-lien AGENTS.md](../../A-lien/AGENTS.md) — full service architecture, DB schema, CLI tree
- [A-lien retposto_sync.py](../../A-lien/src/A_lien/service/retposto_sync.py) — sync mixin source
- [A-lien imap/client.py](../../A-lien/src/A_lien/imap/client.py) — IMAPClient source

## Sync Backlog (IMAP Flag Sync)

Flag changes (read/delete) are synced back to the IMAP server via a backlog queue:

1. **`_imap_sync_flags()` in `MessageOpsService`** — Attempts an immediate IMAP `STORE` via `set_flags()`. Falls back to enqueuing if the connection fails.
2. **`_sync_backlog` table** — Stores pending flag changes with account, folder, IMAP UID, and desired flag state.
3. **`process_sync_backlog()`** — Called after each IMAP sync (`sync_account`) and exposed via `EmailService.process_sync_backlog()`. Connects per-account and flushes up to 500 entries.
4. **IMAP `set_flags()`** in `client.py` — Sends `+FLAGS.SILENT` / `-FLAGS.SILENT` for add/remove operations.

## Domain-Specific Rules for Agents

1. **Fork the service layer, not the CLI.** A-lien's CLI code (Typer commands) stays behind. The services are what matter — they expose the `RetpostoService` and `KontaktoService` APIs.
2. **Rename to English.** `retposto` → `email`, `kontakto` → `contacts`, `mesagoj` → `messages`, `dosierujoj` → `folders`. Update all variable names and comments accordingly.
3. **DB column names use English** — migrated from Esperanto in v0.3.0 (e.g., `subject`, `received_at`, `account_email`).
4. **Simplify the mixin hierarchy.** A-lien uses 7+ mixins composed into a single class. Consider flattening to 2-3 service classes (`EmailService`, `ContactsService`, `AccountService`).
5. **Strip keyring.py** — lighterbird already has one in `core/keyring.py`.
6. **OAuth2 must be added** for modern email providers (Gmail, Outlook). Design the auth interface now even if only password auth is implemented initially.
7. **Adapt error reporting.** A-lien uses `error()`, `info()` from A.core. lighterbird should use Python logging or raise structured exceptions for the server layer to handle.
