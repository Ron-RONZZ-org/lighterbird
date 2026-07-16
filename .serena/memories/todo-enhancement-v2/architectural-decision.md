# Todo Enhancement v2 + Root Command Defaults — Architectural Decision (2026-07-03)

## Issue
https://github.com/Ron-RONZZ-org/lighterbird/issues/75

## Verdict
Modified approval. Three changes vs. original proposal:

1. **Root command default**: Use explicit `default_action` field in tree nodes (opt-in), not a heuristic.
2. **Help autocomplete**: Frontend-only for v0.2.x; backend `--help` meta-flag deferred.
3. **Tags**: Split into CLI flags (Phase 2) + GUI filter UI (Phase 3).

## Key Findings
- Tags infrastructure (DB schema, service methods) is already fully implemented from v0.2.0
- Unified list/tree tab is 90% done — `TodoListTab.svelte` already handles both modes
- UUID partial-match autocomplete already works — cache staleness is the real bug
- `!backup` must NOT default to `list` (its first child is `now`)

## Implementation Phasing
- Phase 1 (2-3d): root-command defaults (backend), cache refresh fix, multi-value testing
- Phase 2 (3-5d): tags CLI/flags, unified list/tree tab, help autocomplete (frontend)
- Phase 3 (2-3d): tags GUI filter UI, root-command default frontend behavior

## Files Affected (expected)
- Backend: `server/command/tree.py`, `server/command/registry.py`, `todo/handlers.py`
- Frontend: `web/src/lib/TodoListTab.svelte`, `web/src/lib/commandEngine.js`, `web/src/lib/popupStore.svelte.js`, `web/src/lib/CommandBar.svelte`
- Tests: multi-value verification for `--dependency`/`--file`
