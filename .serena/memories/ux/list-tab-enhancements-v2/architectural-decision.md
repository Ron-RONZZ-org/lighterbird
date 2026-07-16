# UX Enhancements v2 — Architectural Decision (2026-06-28)

**Issue:** https://github.com/Ron-RONZZ-org/lighterbird/issues/55

## Verdict
Approved. All three proposals align with existing architectural patterns.

## Key Decisions

### P1: Dialog Focus Trapping
- Create `createDialogTrap()` in `listTabShared.svelte.js` — wraps Tab/Shift+Tab within dialog container
- Apply to `ConfirmDialog.svelte`, `MoveDialog.svelte`
- Replace JournalListTab inline confirm div with `<ConfirmDialog>`
- No backend changes

### P2: Add Success → Return to List + Highlight
- List tabs pass `_returnIdKey`, `_returnType` in form `initialData`
- `FormTab.handleFormSubmit()` detects return target, fetches fresh list via `LIST_REFRESHERS`, injects `highlight` = UUID
- All list tabs adopt highlight animation from SieveListTab (2s CSS fade)
- Graceful degradation if UUID absent or list tab closed

### P3: Markdown Detail Views
- New `JournalViewTab.svelte` — journal detail with markdown body
- New `ContactViewTab.svelte` — structured contact detail view
- New dedicated components (not enhancing StatusPopup, which is already a 340+ line god component)
- EventsPopup gets renderMarkdown on description
- Register in TabView.svelte as `"journal-view"`, `"contact-view"`

## Pre-existing Bug Flagged
**idKey inconsistency**: `App.svelte:detectPersistentType()` and `commandRouter.js:resolveListIdKey()` use different idKey strings for same data types (e.g., `"journal"` vs `"journal-list"`, `"todos"` vs `"todo-list"`). Fix in separate issue.

## Implementation Order
1 → 2 → 3 (no code dependencies, but P1 safest, P2 core UX, P3 new components)
