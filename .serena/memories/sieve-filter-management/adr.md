# Sieve Filter Management — Architectural Decision

**Date:** 2026-06-26
**Decision by:** User + architect agent consultation
**GitHub Issue:** [#33](https://github.com/Ron-RONZZ-org/lighterbird/issues/33)

## Verdict
Proposal approved. Sieve filter management is in-scope per AGENTS-email.md and v0.2.0 architectural plan.

## Key Decisions (per @architect)

1. **Local storage**: SQLite table `sieve_skriptoj` in email.db (not filesystem)
2. **Account binding**: `konto_id` FK; ManageSieve config columns on `kontoj` table
3. **Commands**: `!email sieve add|list|view|modify|delete|activate`
4. **REST**: `GET/POST/PUT/DELETE /api/v1/email/sieve/{name}`, `POST .../activate`, `POST .../validate`
5. **Remote sync**: Auto-sync to ManageSieve when configured; local state is authoritative; sync failures are non-fatal
6. **Spam integration**: Synthetic `_spam_blocks` script auto-generated from SpamManager
7. **Validation**: `validate_sieve()` via optional `sievelib`; graceful fallback
8. **Read-only protection**: Scripts starting with `_` are system scripts (read-only)

## New Files
- `email/services/sieve.py` — SieveService
- `server/routes/email_sieve.py` — REST endpoints
- `server/command/handlers/email_sieve.py` — command handlers
- `web/src/lib/SieveListTab.svelte` — list table
- `web/src/lib/SieveEditorForm.svelte` — script editor

## Modified Files
- `email/db.py` — schema additions
- `email/filters/spam.py` — _spam_blocks auto-update
- `server/schemas.py` — Sieve models
- `server/routes/__init__.py` — register router
- `server/command/handlers/email.py` — managesieve flags
- `web/src/lib/api.js` — sieve API methods
- `web/src/lib/commandTree.js` — autocomplete subtree
- `web/src/lib/TabView.svelte` — tab type routing

## Implementation Order
1. Schema + migrations
2. Service layer
3. Pydantic schemas
4. REST routes
5. Command handlers
6. ManageSieve CLI flags
7. Spam block integration
8. Frontend API + autocomplete
9. GUI components
10. TabView routing
11. Tests
