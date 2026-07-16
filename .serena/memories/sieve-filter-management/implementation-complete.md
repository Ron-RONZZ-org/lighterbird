# Sieve Filter Management — Implementation Complete

**Date:** 2026-06-26
**Commit:** 884e45f
**Issue:** #33 — https://github.com/Ron-RONZZ-org/lighterbird/issues/33

## What was implemented

Full Sieve filter management: CLI commands (`!email sieve *`), REST API, and GUI management pane.

### Backend files created
- `src/lighterbird/email/services/sieve.py` — SieveService (CRUD + ManageSieve sync)
- `src/lighterbird/server/routes/email_sieve.py` — REST endpoints
- `src/lighterbird/server/command/handlers/email_sieve.py` — command handlers

### Backend files modified
- `src/lighterbird/email/db.py` — added sieve_skriptoj table + managesieve columns
- `src/lighterbird/email/service.py` — added self.sieve
- `src/lighterbird/email/services/__init__.py` — exported SieveService
- `src/lighterbird/server/app.py` — registered sieve router
- `src/lighterbird/server/schemas.py` — Sieve Pydantic models
- `src/lighterbird/server/command/handlers/email.py` — managesieve flags on account modify
- `src/lighterbird/server/command/handlers/__init__.py` — imported sieve handler
- `src/lighterbird/server/command/tree.py` — sieve subtree in command tree

### Frontend files created
- `web/src/lib/SieveListTab.svelte` — list table with actions
- `web/src/lib/SieveEditorForm.svelte` — editor with validation

### Frontend files modified
- `web/src/lib/api.js` — sieve API methods
- `web/src/lib/commandTree.js` — autocomplete subtree
- `web/src/lib/TabView.svelte` — tab routing + icons

### Key design decisions
- Local state is authoritative; ManageSieve sync failures are non-fatal
- System scripts (`_` prefix) are read-only
- `sievelib` is optional; validation falls back gracefully
- Script activation auto-deactivates previously active script
- If >1 account has ManageSieve, --account flag is required
