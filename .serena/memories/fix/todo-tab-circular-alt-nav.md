# Fix: TodoListTab circular dependency + Alt+N/P tab navigation

## Date
2026-07-03

## Bugs Fixed

### Bug 1: TodoListTab TDZ error (`Cannot access 'g' before initialization`)
**Root cause**: Circular dependency between `isTree` ($derived) and `displayMode` ($state):
```js
let isTree = $derived(displayMode === "tree"); // reads displayMode (TDZ!)
let displayMode = $state(isTree ? "tree" : "flat"); // reads isTree
```
Svelte 5 compiled `$derived` before `$state`, so `isTree` accessed `displayMode` in TDZ.

**Fix**: Removed circular dependency:
```js
let displayMode = $state(data?.tree ? "tree" : "flat");
let isTree = $derived(displayMode === "tree");
```

**Systematic review**: Checked all list tabs for same pattern — only TodoListTab had it.

### Bug 2: Alt+N/P tab navigation not working
**Fix**: Added Alt+N (next tab) and Alt+P (previous tab) handlers in `App.svelte`'s `handleGlobalKeydown` with wrap-around. Updated KeyboardShortcutOverlay docs.

## Test Results
- 203/203 backend tests pass
- 28/28 E2E tests pass (no more `[BROWSER ERROR] Cannot access 'g' before initialization`)
- 11/11 basic Playwright tests pass
