# Svelte 5 Warnings Fixed (2026-07-11)

## Warnings Fixed
1. **Unused CSS `.preview-btn`** in `ComposeEmail.svelte`: Removed dead CSS selectors that had no corresponding HTML elements.
2. **alertdialog a11y** in `HomeTab.svelte`: Added `tabindex="-1"` and keyboard (Escape) event handler to clear-overlay dialog.
3. **state_referenced_locally** in `FormTab.svelte`: `let formError = $state(data?.error || "")` captures the initial value only. Fixed by using `$state('')` + `$effect` to sync from prop.
4. **non_reactive_update** in `AdvancedSearchDialog.svelte`: `let overlay` needs `$state` when used with `bind:this` in Svelte 5.
5. **slot_element_deprecated** in `ListSearchBar.svelte`: `<slot name="actions">` → `{#snippet actions()}` / `{@render actions?.()}`. Updated all 6 consumer components.

## Email List Bug Investigation
Investigated "!email list tab always no email shown even after successful syncing". The bug was caused by `refreshList()` using `tabStore.active.id` at sync completion time (30-120s later). If the user switched tabs during the long sync, the result was applied to the wrong tab. This was fixed in commits `cef05ea` and `b121eae`. Current `findByKey("persistent-email-list")` approach works correctly.

## Testing
- `npx vite build`: Build succeeds with zero warnings
- `pytest tests/test_server/test_routes_email.py tests/test_email/test_email.py`: 38/38 pass
- `npx vitest run` in web/: 96/96 pass
- Browser testing: `!email list` shows messages, sync updates list correctly
