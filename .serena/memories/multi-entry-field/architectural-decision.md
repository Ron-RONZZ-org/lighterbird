# Multi-Entry Field Component + Letter/Todo Tag Enhancements — Architectural Decision

## Issue
https://github.com/Ron-RONZZ-org/lighterbird/issues/87

## Verdict
Approved. All 4 items align with AGENTS.md conventions.

## Scope Summary
- **Items 1-3**: Implementation work (no architectural changes needed)
- **Item 4 (MultiEntryField)**: **Architectural** — new shared component design approved (see issue for full API spec)

## Key Findings
- All backend flags already exist (`--tag`, `--dependency`, `--tags`, `--mode`)
- Letter tag AND filtering already works on backend (`EXISTS` per tag in `letter/services/letters.py:61-67`)
- Todo toggle button exists, just missing `t` keyboard shortcut
- Tags field is missing from `TodoAddForm.svelte` entirely
- Multi-entry fields (cc/bcc, dependency, tags) have 5+ ad-hoc implementations — unification overdue

## Implementation Order
1. Todo list `t` key (trivial)
2. MultiEntryField component (architectural foundation)
3. Letter tags GUI (uses MultiEntryField in filter mode)
4. Todo add tags+dependency (uses MultiEntryField)

## Risk Mitigations
- All multi-value fields join to comma-separated on submit (no backend API breakage)
- Chip interactions use `e.stopPropagation()` to avoid keyboard handler conflicts
- Component split into .svelte + .js if >500 lines
- `$bindable()` requires Svelte 5 (already in use)

## Files Affected (expected)
- New: `web/src/lib/MultiEntryField.svelte`
- Modified: `TodoListTab.svelte`, `TodoAddForm.svelte`, `LetterListTab.svelte`, `LetterForm.svelte`, `ComposeEmail.svelte`, `AGENTS.md`
