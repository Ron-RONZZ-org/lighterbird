# Sieve Activation UX Redesign — Architectural Decision

**Date:** 2026-06-26
**Decision by:** User + architect agent consultation
**GitHub Issue:** [#37](https://github.com/Ron-RONZZ-org/lighterbird/issues/37)

## Key Decisions

1. **Activation model**: Priority order (multiple scripts per account, not one-active)
2. **Combining**: New `email/filters/combiner.py` — regex-based require extraction + dedup
3. **Conflict detection**: Non-blocking warnings only (duplicate fileinto, multiple vacation, shadowed stop)
4. **Conflict API**: Separate `POST /analyze` endpoint (not part of /validate)
5. **GUI**: New `ActivationModal.svelte` with search bar + active/available lists + bulk buttons
6. **Backward compat**: No migration needed — only application logic changes

## New Files
- `email/filters/combiner.py` — combine_scripts() + check_conflicts()
- `email/services/sieve_activation.py` — extracted activation management
- `web/src/lib/ActivationModal.svelte` — GUI modal

## Modified Files
- `email/db.py` — priority column + migration
- `email/services/sieve.py` — remove exclusive deactivation
- `server/schemas.py` — new models
- `server/routes/email_sieve.py` — new endpoints
- `server/command/handlers/email_sieve.py` — CLI updates
- `server/command/tree.py` — new subcommands
- `web/src/lib/SieveListTab.svelte` — replace per-row buttons
- `web/src/lib/api.js` — new API methods

## Implementation Order
Phase 1: combiner.py + schema + schemas
Phase 2: service layer changes
Phase 3: API + CLI updates
Phase 4: frontend
