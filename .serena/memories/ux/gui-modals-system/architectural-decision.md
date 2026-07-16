# GUI Modals for All CLI Commands — Architectural Decision (2026-06-28)

## Issue
https://github.com/Ron-RONZZ-org/lighterbird/issues/51

## Verdict
Approved with modifications per @architect review.

## Key Architectural Decisions

1. **Unified FormTab pattern** — `FormTab.svelte` is the single entry point for ALL command forms. Remove inline form rendering from `StatusPopup.svelte` and `ContactsListTab.svelte`.

2. **Two-path auto-open**:
   - **Primary:** Frontend `commandRouter.js` interception (zero backend round trips) — already partially implemented, needs integration with `App.svelte.handleCommand()`
   - **Fallback:** Backend `routes/command.py` returns `{type: "form-required", form: "...", initialData: {...}}` for saved-commands/aliases that can't be expanded frontend-side

3. **4-level form strategy:**
   - Level 1: Dedicated forms for complex UIs (email.send, todo.add, sieve.*)
   - Level 2: Structured simple forms from tree metadata (contacts, accounts, templates)
   - Level 3: Generic dynamic forms (backup config, sync)
   - Level 4: No forms — ConfirmDialog only (remove, trash, done)

4. **Shared infrastructure to extract:**
   - `FormField.svelte` (P0), `UuidPicker.svelte` (P0)
   - `DynamicForm.svelte` (P1), `createFormState()` (P1)
   - `formShared.css` (P1)

5. **CommandValidationError unchanged** — form-required replacement handled at route layer, not in handlers.

6. **Password fields** — add `sensitive: true` metadata to flag definitions for `<input type="password">`.

## Implementation Order (5 Phases)
1. Unify form patterns
2. Shared infrastructure
3. DynamicForm + Level 2/3 commands
4. Dedicated Level 1 forms
5. Fallback backend integration

## Commands NOT requiring forms
list, view, read, search, trash, archive, done, remove, help, backup.now, llm.prompt, profile.show/clear/list
