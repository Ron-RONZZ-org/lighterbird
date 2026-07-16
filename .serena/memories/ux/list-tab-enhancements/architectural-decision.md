# List Tab UX Enhancements — Architectural Decision

**Date:** 2026-06-26
**Decision by:** User + architect agent consultation
**GitHub Issue:** [#34](https://github.com/Ron-RONZZ-org/lighterbird/issues/34)

## Part A: Post-command navigate to list + highlight

**Decision:** Change backend response type to list type (Option A).
- `!email sieve add/modify` returns `type: "sieve-list"` instead of `type: "status"`
- Adds `highlight: "script-name"` field for row animation
- Frontend `popupStore.show()` auto-detects `*-list` types and sets `idKey` for tab dedup
- `SieveListTab` receives `highlight` prop, applies 2s CSS fade animation via reactive state

## Part B: UUID copy to clipboard

- Click handlers on UUID elements in EmailListTab, JournalListTab, SieveListTab
- Uses `navigator.clipboard.writeText()` (pattern already in HomeTab.svelte)
- Visual feedback: "Copied!" text replaces truncated UUID for 1.2s

## Implementation Order
1. Backend: sieve_add/modify return type: sieve-list + highlight
2. Frontend: popupStore idKey auto-detection
3. Frontend: SieveListTab highlight + UUID copy
4. Frontend: SieveEditorForm pass highlight on save
5. Frontend: EmailListTab UUID copy
6. Frontend: JournalListTab UUID copy

## Key Design Rules
- Steps 1-3 must deploy together
- Highlight auto-clears after 2s via timer
- Editor save path also passes highlight
