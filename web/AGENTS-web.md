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
  - As-you-type autocomplete with UUID and label-based suggestion dropdown
  - `/*` autocomplete shows prompt command names and descriptions
  - Arrow key history navigation (up/down through command history)
  - Tab completion for command names, flags, and folder paths
  - Disabled with animated spinner while command is running
- **Tab-based output** — each command result opens as a new tab in the tab bar (below the output area). Supported tab types:
  - Status lists (messages, accounts, contacts, todos, journals)
  - Rich HTML email body (fallback to plain text) with toolbar (Reply, Reply All, Forward, Mark Read, Trash, Thread sidebar)
  - Calendar events
  - Error reports with actionable suggestions
  - Help/command reference
  - Loading state with prominent spinner and "avoid clicking" hint
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
- **`BannerContainer.svelte`** — Mounted once in `App.svelte`. Renders a fixed-position auto-dismissing banner (3s default).
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

## GUI Style Conventions

All new UI components must follow these established conventions:

### Color Palette

| Role | Hex | Usage |
|------|-----|-------|
| Background | `#1a1a2e` | Main page/dialog background |
| Surface | `#16162a` | Toolbar, sidebar, card backgrounds |
| Surface hover | `#1e1e32` | Dialog backgrounds |
| Border | `#333` / `#444` | Default borders |
| Border accent | `#4a4a6a` / `#6a6a9a` | Focus/active borders |
| Text primary | `#e0e0e0` | Body text |
| Text muted | `#7c7c9a` / `#5a5a7a` / `#555` | Labels, hints, disabled |
| Primary action | `#7fdb7f` green tint (`#3a6a3a` border) | +New, Save, Confirm buttons |
| Danger action | `#d06` / red tint (`#6b2020` bg, `#8b3030` border) | Delete buttons |
| Accent blue | `#7c9bff` / `#3a5a8a` bg | Action buttons, links |
| Input bg | `#12122a` | Text inputs, search fields |
| Hover | `#2a2a3e` / `#2a2a4e` / `#3a3a5e` | Button hover states |
| Active | `#2a2a50` | Active/toggled buttons |

### Toolbar / Navbar Pattern

All list tab toolbars follow a **flex layout with three zones**:

```
[ left (buttons) ]        [ center (hints) ]        [ right (actions) ]
```

- Background: `#16162a`, bottom border: `1px solid #333`
- Height: `min-height: 2.2rem`, padding: `0.3rem 0.5rem`
- Font: `monospace`, size: `0.82rem`

### Tool Buttons (`.tool-btn`)

Every action button in toolbars uses this class:

```css
.tool-btn {
  padding: 0.25rem 0.6rem;
  border: 1px solid #444;
  border-radius: 4px;
  background: #2a2a3e;
  color: #e0e0e0;
  cursor: pointer;
  font-family: monospace;
  font-size: 0.78rem;
  transition: background 0.1s, border-color 0.1s;
  white-space: nowrap;
}
```

Variants:
- **Active**: `border-color: #6a6a9a; background: #2a2a50;`
- **Primary** (green): `border-color: #3a6a3a; color: #7fdb7f;`
- **Danger** (red): `.tool-btn.danger:hover { background: #6b2020; border-color: #8b3030; }`

### Keyboard Shortcut Badges (`<kbd>`)

Shortcuts inside buttons use inline `<kbd>` elements:

```css
.tool-btn kbd {
  display: inline-block;
  padding: 0 3px;
  margin-left: 2px;
  font-family: monospace;
  font-size: 0.68rem;
  background: #222;
  border: 1px solid #555;
  border-radius: 3px;
  color: #999;
  line-height: 1.3;
}
```

Every toolbar button visible in view mode should show its keyboard shortcut in a `<kbd>` badge.

### Dialog / Overlay Pattern

Modals follow this structure:

```html
<div class="overlay" onclick={onClose} role="dialog" aria-modal="true">
  <div class="dialog" onclick={(e) => e.stopPropagation()} role="document">
    <!-- content -->
  </div>
</div>
```

- Overlay: `position: fixed; inset: 0; background: rgba(0,0,0,0.65); z-index: 300;`
- Dialog: `background: #1e1e32; border: 1px solid #444; border-radius: 10px; padding: 1.5rem;`

### Search / Filter Tile Bar

Active search conditions are displayed as removable tiles:

- Tile: `background: #2a2a50; border: 1px solid #4a4a7a; border-radius: 4px; padding: 0.15rem 0.4rem;`
- Tile label: `.7rem, uppercase, #7c7c9a`
- Tile value: `#e0e0ff, max-width: 200px, text-overflow: ellipsis`
- X button: no background, `#7c7c9a`, `hover: #f06060`
- Bar: `background: #1e1e32; border-bottom: 1px solid #333; padding: 0.25rem 0.75rem; flex-wrap: wrap;`

### General Rules

- **Monospace everywhere**: `font-family: monospace` on all structural elements
- **Consistent border-radius**: `4px` for inputs, buttons, panels; `10px` for dialogs
- **No border-radius on bottom of panels that touch another element** (e.g., list rows within a scroll container)
- **At least 3:1 contrast ratio** on all text against backgrounds
- **Keyboard-first navigation**: every interactive element must be reachable and operable by keyboard
- **Animations**: keep under 150ms for hover/transition effects; no keyframe animations on structural elements
