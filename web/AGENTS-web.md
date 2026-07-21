# AGENTS-web.md — Web Frontend Agent Instructions

## Summary

Svelte 5 SPA providing the lighterbird user interface. The core interaction model is a centralized command bar (`!` commands) with rich result rendering for email reading, calendar views, todo lists, and LLM chat.

## Purpose and Expected Behavior

The web frontend provides:

- **Home tab** — persistent pinned tab at index 0, non-closable, always present. This is the default view. It contains:
  - lighterbird logo/wordmark in the upper center of the screen
  - Command bar (`❯` input) in the **lower center** of the screen
  - Empty content area (no results until a command is run)
- **Command bar** — text input area with:
  - `!` prefix → execute a structured command (`!email list`, `!new`, `!search`)
  - `/*` prefix → execute a file-based prompt command (`/*weekly INBOX`, `/*summarize`)
  - no `!` or `/*` prefix → send as LLM chat message
  - **Multi-command input**: when first char is `!`, multiple commands separated by `!` boundary are accepted: `!email list !todo list`. Commands execute sequentially, continue-on-error. Interactive/form commands are skipped. `!` inside quoted strings is not treated as a boundary.
  - As-you-type autocomplete with UUID and label-based suggestion dropdown
  - `/*` autocomplete shows prompt command names and descriptions
  - Arrow key history navigation (up/down through command history)
  - Tab completion for command names, flags, and folder paths
  - Disabled with animated spinner while command is running
- **Tab-based output** — each command result opens as a new tab in the tab bar (below the output area). Supported tab types:
  - Status lists (messages, accounts, contacts, todos, journals, email drafts)
  - Rich HTML email body (fallback to plain text) with toolbar (Reply, Reply All, Forward, Mark Read, Trash, Hard Del, Spam, Fraud, Export, Print, Thread sidebar)
  - Calendar events
  - Error reports with actionable suggestions
  - Help/command reference
  - Loading state with prominent spinner and "avoid clicking" hint
- **ActionBanner** — undo-capable banner rendered at the top of TabView for email operations (trash, hard-delete, spam, fraud). Shows a message with an "Undo" button. Auto-dismisses after 5 seconds. Clicking Undo calls `POST /api/v1/email/actions/undo/{operation_id}` to revert the operation. Powered by `actionBannerStore.svelte.js` (module-level `$state` singleton).
- **Email view tab** — `EmailViewTab.svelte` provides full keyboard shortcuts: `Delete` (soft-delete), `Ctrl+Delete` (hard-delete), `Ctrl+S` (report spam), `Ctrl+Shift+S` (report fraud). After an action, dispatches `email-deleted` custom event (handled in App.svelte to update list tabs), navigates to next unread email, and shows an ActionBanner with undo.
- **Tab bar** — horizontal row at bottom of output area. Features:
  - Left-click tab to switch; ✕ button to close (all tabs except home are closable)
  - Alt+1/2/3/4 keyboard shortcuts to switch tabs
  - Tab icon + truncated title
  - Home tab always first, showing logo/command bar when active
- **Full-screen output** — when a result tab is active, its content takes all available screen space (no wasted margins). The command bar is accessible by switching back to the home tab (Alt+1) or typing a new command from any tab.
- **Conversation sidebar** — slides in from right on email detail tabs, shows thread history with clickable links
- **Top progress bar** — thin animated gradient bar across the full viewport width while any command is loading, visible regardless of which tab is active

## Layout

```
┌─────────────────────────────────────────┐
│                                         │
│         ◇ lighterbird ◇                 │  ← logo (upper center, home tab only)
│                                         │
│                                         │
│                                         │
│         ❯ Type !command...              │  ← command bar (lower center, home tab only)
│                                         │
├─────────────────────────────────────────┤
│  [Home] [Inbox ✕] [Email... ✕]  [...]  │  ← tab bar (always visible)
└─────────────────────────────────────────┘

When a result tab is active:
┌─────────────────────────────────────────┐
│  ┌─────────────────────────────────┐    │
│  │ tab content (full screen)       │    │
│  │                                 │    │
│  └─────────────────────────────────┘    │
│  [Home] [Inbox ✕] [Email ✕]  [...]  │  ← tab bar
└─────────────────────────────────────────┘
```

## Constraints and Invariants

- **Home tab is always at index 0, never closable.** Switch to it via Alt+1 or by closing all result tabs.
- **Command bar lives on the home tab only** (lower center). When viewing result tabs, the command bar is not visible — type a new `!` command or use Alt+1 to go home. The top progress bar is the only loading indicator that spans all tabs.
- **No routing library initially** — single-page, command-driven. Tab switching is local Svelte state, not URL-based.
- **State kept in Svelte stores** — no Redux/Pinia. Svelte 5 `$state` runes for reactive state. `tabStore` manages tabs; `popupStore` acts as backward-compat bridge.
- **API calls via `fetch()`** — no Axios or heavy HTTP client. A thin `api.js` wrapper is enough.
- **WebSocket for LLM streaming** — separate connection from REST API.
- **No TypeScript initially** — plain JavaScript. TypeScript can be added later if the codebase grows.
- **Bundle size target: under 100 KB gzipped** — lighterbird is supposed to be lightweight.
- **Works offline for cached data** — service worker can be added later; not a v1 requirement.

## Input/Output Expectations

- `GET /api/v1/...` — fetch data (messages, contacts, events, folders)
- `POST /api/v1/...` — create/update data
- `WebSocket /api/v1/ai/chat` — send message, receive streaming response
- `WebSocket /api/v1/ai/command` — send `!` command, receive structured result

## Svelte 5 Reactive Best Practices

### Always key `{#each}` blocks

Provide a unique key `(item.id)` for every `{#each}` block that contains event
handlers or mutable state. Index-based matching (`item, i`) can produce stale
closures when items are dynamically added/removed, causing event handlers to
reference the wrong data or silently fail.

```svelte
<!-- BAD -->
{#each tabStore.tabs as tab, i}
  <button onclick={() => closeTab(tab.id)}>✕</button>
{/each}

<!-- GOOD -->
{#each tabStore.tabs as tab (tab.id)}
  <button onclick={() => closeTab(tab.id)}>✕</button>
{/each}
```

### Consolidate module-level $state writes in a single $effect

When a component writes to module-level `$state` variables (stores defined in
`.svelte.js` files with `$state(new Map())` or similar), use ONE `$effect` for
ALL such writes. Each `$state` reassignment inside an `$effect` increments
Svelte 5's internal batch flush counter. During mount, the combined depth of
multiple effects writing to module-level stores can exceed the 1000-iteration
guard, throwing `effect_update_depth_exceeded` and silently corrupting all
event handlers (tab close buttons, keyboard shortcuts).

```javascript
// BAD — two separate effects, each contributes to flush depth
$effect(() => { storeA.set(tabId, value); });
$effect(() => { storeB.set(tabId, value); });

// GOOD — single effect with deferred write for the second store
$effect(() => {
  storeA.set(tabId, value);
  queueMicrotask(() => storeB.set(tabId, value));
  return () => { storeA.clear(tabId); storeB.clear(tabId); };
});
```

### Debugging silent event-handler failures

When keyboard shortcuts, tab close buttons, or other event handlers appear
"dead" (no response to clicks/keys, no console errors):

1. **Check for `effect_update_depth_exceeded`** — This Svelte 5 error is
   NOT logged to `console.error`. Use `page.on("pageerror", ...)` in
   Playwright to detect it. In Vite, look for the error URL
   `https://svelte.dev/e/effect_update_depth_exceeded` in browser devtools
   or the terminal.
2. **Consolidate concurrent `$effect` writes** to module-level `$state`
   (see rule above).
3. **Verify `{#each}` keys** — missing unique keys can cause stale closures.

### Mock strategy for Svelte 5 component tests

`@testing-library/svelte` v5.x cannot render Svelte 5 components with mock
child `.svelte` stubs — the test harness fails with "Class constructors
cannot be invoked without 'new'". Instead:

- Mock at the **module-import level**: mock `.js` stores, API clients, and
  utility modules rather than child `.svelte` component files.
- Test child `.svelte` components **independently** in their own test files.
- Use **Playwright E2E scripts** for integration testing that spans multiple
  components.

## Documentation Reference

- Svelte 5 docs: https://svelte.dev/docs/svelte/overview
- Vite docs: https://vitejs.dev/
- `svelte-spa-router`: https://github.com/ItalyPaleAle/svelte-spa-router

## Development Setup

```bash
cd web
npm install
npm run dev          # Vite dev server (port 6005)
npm run build        # Build to web/dist/
```

The Vite dev server proxies `/api/` requests to the FastAPI backend. By default it connects to port 6006. To use a different backend port, set the `LIGHTERBIRD_PORT` environment variable:

```bash
LIGHTERBIRD_PORT=8764 npm run dev
```

This is the same env var read by `python -m lighterbird` and `lighterbird-dev` to determine which port to bind.

## Post-Send Banner

When `!email send` / reply / forward completes, a temporary confirmation banner is shown:

- **`bannerStore.svelte.js`** — Reactive store exposing `banner.show(msg, type, duration?)` and `banner.dismiss()`.
- **`BannerContainer.svelte`** — Imported from `@lightercore/ui/BannerContainer.svelte`. Mounted once in `App.svelte`. Renders a fixed-position auto-dismissing banner (3s default). Supports `success`, `error`, `info`, and `warning` types. Persistent banners (duration=0) have word-break styling. The local copy was deleted in favor of the lightercore version.
- **`SyncOverlay.svelte`** — Full-page blocking overlay with animated spinner and progress bar. Used by `EmailListTab` and `EmailFolderTab` during initial IMAP sync. Shows current folder name, folder count, and total messages. Mounted via `{#if initialLoading && syncing}` condition at the top of each tab's template.
- **`FolderContextMenu.svelte`** — Right-click context menu for `EmailFolderTab` tree nodes. Positioned at cursor coordinates. Offers Rename and Delete actions. Closes on Esc or click-outside.
- **`FolderDeleteDialog.svelte`** — 2-level delete confirmation dialog for folder deletion. **Level 1**: Radio buttons for email disposition (move to Trash / move to another folder). **Level 2**: Autocomplete destination folder input (shown only when "move to another folder" is selected). Syntax: `{email}/{folder}`. Uses existing `batchMove` API + `deleteFolder` API sequentially.
- **`FormTab.svelte`** — After successful email send, calls `banner.show("Email sent ✓", "success")` before redirecting to the email list tab.

## HTML/Plain Text Persistence

The HTML/plain text toggle in `EmailViewTab.svelte` is persisted across emails via `localStorage` key `lighterbird:email:viewHtml`. Default is `true` (HTML).

## Domain-Specific Rules for Agents

1. **The command bar is the star.** Spend 80% of effort getting the command bar right (autocomplete, history, suggestions, keyboard navigation). The rest of the UI is secondary.
2. **Keep it simple.** No Vue, no React, no Tailwind (plain CSS or a minimal utility lib). The app should load fast on a slow connection.
3. **No page reloads.** Everything is client-side rendered. Commands fetch data via API and update the DOM in-place.
4. **Mobile-friendly command bar.** The input must be usable on mobile keyboards (avoid tiny fonts, ensure proper viewport).
5. **LLM streaming is a must.** The command bar should show LLM responses as they stream in, not all at once.
6. **Accessibility basics.** The command bar needs an `<input>` with proper ARIA labels, role="combobox" pattern for autocomplete, and keyboard-only navigation.
7. **Build output goes to `web/dist/`** — the FastAPI server mounts this directory as static files.
8. **Do not use SvelteKit** — this is a SPA, not an SSR app. SvelteKit would add unnecessary complexity and bundle size.
9. **List tabs are persistent; detail tabs append.** List views (accounts, calendars, contacts, todos, journal entries, email list) are persistent — re-running the same command replaces the previous list tab (keyed by PersistentDataType). Detail views (individual email message, single contact, etc.) always append as new tabs. Loading tabs close when the result arrives. The home tab is pinned at index 0 and never closes.
10. **In-tab filter/search bars are exceptions to rule #8.** The EmailListTab has a toggleable search bar (`f` key) that filters the current message list via REST API calls. This is not a command bar — it cannot run `!` commands, only text-search the current view. Similar filter bars in other list views are acceptable if they stay scope-limited to the current data set.
11. **Folder paths use `{email}/{folder}` convention.** Auto-completion for `--folder` flags inserts the full folder path, not a UUID.
12. **Shared preview components.** `web/src/lib/PreviewDialog.svelte` is a reusable modal for rendering HTML content preview. Use it with `createPreviewState()` from `web/src/lib/preview.svelte.js` whenever a form has HTML/markdown/plain text input that the user may want to preview before submitting. Call `preview.show(content, format, title)` to open the dialog; `preview.close()` to dismiss. The utility also exports `showPreviewInTab(content, format)` for opening rendered content in a new browser tab.
13. **Unified email preview in ComposeEmail.** The ComposeEmail form no longer has separate "Preview Body" and "Preview Signature" buttons. A single "Preview Email" button calls `POST /api/v1/email/preview` which returns a complete HTML rendering of the subject, body (converted per body_format), signature (converted per its format), and attachment filenames. This replaces the two-element preview approach and ensures the preview matches what the SMTP send path produces.
14. **Command history is persistent (`localStorage`).** The `commandHistory.svelte.js` module persists the last 100 command/chat entries to `localStorage` key `lighterbird:commandHistory`. Up/Down arrow navigation works across page refreshes. Duplicate consecutive entries are collapsed to a single entry.
15. **Preview buttons show key hints.** All preview buttons (`DynamicForm`, `JournalWrite`, `ComposeEmail`) display a visible `<kbd>Ctrl+Shift+P</kbd>` badge in the button label, matching the existing `<kbd>` pattern used for `Ctrl+S` and `Ctrl+Enter` hints.
16. **Form error preservation.** `FormTab.handleFormSubmit()` keeps the form tab open on submission failure (HTTP error or network error). An inline red error banner is shown above the form content, and a temporary `banner.show(msg, "error")` notification also fires. The user can correct their input and retry without losing data. On success, the form closes and navigates to the appropriate list tab (existing behavior).
17. **Signature format dropdown.** Email signatures support `--format` (plain/html/markdown). `DynamicForm.svelte` renders a `<select>` for flags that include a `values` array in their tree metadata (e.g., `{"values": ["plain", "html", "markdown"]}`).
18. **Multi-command input is frontend-only.** `HomeTab.svelte` handles multi-command detection (`isMultiCommand`) and batch execution. The shared parsing utility (`splitCommands` / `isMultiCommand`) lives in `@lightercore/ui/multiCommand.js`. Interactive commands (forms) are skipped with an error in batch mode. No backend changes needed — each command is sent as a separate `POST /api/v1/command` call.
19. **Mutation redirect with highlight.** After a successful `!xxx add/modify/delete` command (direct execution, all required params provided), `App.svelte` redirects to the corresponding list tab instead of showing a transient popup. The affected entry is briefly highlighted with a 2s CSS fade animation (except on delete, where the entry is gone). Uses a hybrid refresh strategy: inject highlight into existing list tabs for add/modify (no loading flicker), always re-fetch for delete. The routing logic and mapping table live in `web/src/lib/mutationToTab.js`. The same pattern was previously a special case only for `!email send`; it now covers all domains: todo, contact, journal, calendar event, letter, sieve, and email send/trash/archive.
20. **EmailFolderTab blocks on sync with full-page overlay.** `EmailListTab` and `EmailFolderTab` both show a blocking `SyncOverlay` (full-page spinner + progress bar) on mount. The overlay is shown while the async IMAP sync runs (`POST /api/v1/email/sync/start` + polling). Only after sync completes does the tab render fresh data. The `initialLoading` state flag controls visibility. Sync is also triggerable manually (Ctrl+R / Sync button). This prevents stale-data conflicts — the user never interacts with cached data that will be replaced mid-session.
21. **Notice banner is home-page only.** The server-notice banner (e.g., "Your system_prompt.md mentions specific ! commands") is wrapped in `{#if tabStore.isHome}` in `App.svelte`. It does not appear on non-home tabs.
22. **Folder tab features.** The `EmailFolderTab` implements the full List Tab Standard Feature Set plus: active element tracking (click-to-highlight with blue left-border), right-click context menu (Renames/Delete), double-click to rename, DELETE key to delete active/selected folders, drag-to-move (drop onto another folder to nest), and a 2-level FolderDeleteDialog that asks what to do with contained emails (move to Trash / move to another folder with autocomplete). The `EmailTreeNode` component accepts `showCheckboxes` prop — the panel always shows checkboxes, the tab hides them outside selection mode.

## GUI Style — Imitate Existing Components

**Do not write custom CSS from scratch.** All new UI components must imitate the styling patterns found in these canonical source files:

| Pattern | Reference file | Key elements to imitate |
|---------|---------------|------------------------|
| Toolbar buttons | `EmailListToolbar.svelte` | `.tool-btn` class, `<kbd>` shortcuts, `left/center/right` flex layout |
| List views | `EmailListTab.svelte` | Monospace font, row layout, selection mode, empty state |
| Dialogs/overlays | `AdvancedSearchDialog.svelte` | `.overlay` + `.dialog` pattern, close on backdrop click |
| Filter/search tiles | `SearchTileBar.svelte` | Tile layout, removable `✕` button, "Clear all" |
| Forms | `DynamicForm.svelte` | Field layout, label/input spacing, validation errors |
| Colors | Any `.svelte` file in `web/src/lib/` | Dark theme: `#1a1a2e` bg, `#e0e0e0` text, `#444` borders |

**Rules to follow:**
- Use `font-family: monospace` on all structural elements
- Use `border-radius: 4px` for buttons/inputs, `10px` for dialogs
- All interactive elements must be keyboard-reachable
- Animations: keep under 150ms; no keyframe animations on structural elements
- **Never duplicate CSS patterns** — import shared components (`ListSearchBar.svelte`, `PreviewDialog.svelte`, `ConfirmDialog.svelte`) instead of re-creating them
- **LLM tool approval dialog**: `ConfirmToolDialog.svelte` is a thin re-export of `@lightercore/ui/ConfirmDialog.svelte`. The shared dialog provides approve/reject per item, per-item + global feedback, and an approve-all toggle. Backward-compatible: accepts both `onConfirm(decisions)` and `onSubmit(decisions, feedback)` callbacks.
- If you need a new component, model it after the closest existing component above
