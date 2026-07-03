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
  - no `!` prefix → send as LLM chat message
  - As-you-type autocomplete with UUID and label-based suggestion dropdown
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
npm run dev          # Vite dev server (port 5173)
npm run build        # Build to web/dist/
```

The Vite dev server proxies `/api/` requests to the FastAPI backend (port 8000).

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
