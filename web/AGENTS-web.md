# AGENTS-web.md — Web Frontend Agent Instructions

## Summary

Svelte 5 SPA providing the lighterbird user interface. The core interaction model is a centralized command bar (`!` commands) with rich result rendering for email reading, calendar views, todo lists, and LLM chat.

## Purpose and Expected Behavior

The web frontend provides:

- **Command bar** — always-visible text input at the top of the screen
  - `!` prefix → execute a structured command (`!account list`, `!new`, `!search`)
  - no `!` prefix → send as LLM chat message
  - As-you-type autocomplete and suggestion dropdown
  - Arrow key history navigation (up/down through command history)
  - Tab completion for command names and options
- **Output area** — below the command bar, renders command results
  - Plain text output (status messages, lists)
  - Rich HTML blocks (rendered email messages, calendar grids)
  - Form panels (compose email, edit contact, create event)
  - Streaming LLM response (token-by-token display)
- **Split view** (optional) — email list + reading pane side by side

## Constraints and Invariants

- **No routing library initially** — single-page, single-view. Command output replaces the content area.
- **State kept in Svelte stores** — no Redux/Pinia. Svelte 5 `$state` runes for reactive state.
- **API calls via `fetch()`** — no Axios or heavy HTTP client. A thin `api.js` wrapper is enough.
- **WebSocket for LLM streaming** — separate connection from REST API.
- **No TypeScript initially** — plain JavaScript. TypeScript can be added later if the codebase grows.
- **Bundle size target: under 100 KB gzipped** — lighterbird is supposed to be lightweight.
- **Works offline for cached data** — service worker can be added later; not a v1 requirement.

## Input/Output Expectations

- `GET /api/v1/...` — fetch data (messages, contacts, events)
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

## Domain-Specific Rules for Agents

1. **The command bar is the star.** Spend 80% of effort getting the command bar right (autocomplete, history, suggestions, keyboard navigation). The rest of the UI is secondary.
2. **Keep it simple.** No Vue, no React, no Tailwind (plain CSS or a minimal utility lib). The app should load fast on a slow connection.
3. **No page reloads.** Everything is client-side rendered. Commands fetch data via API and update the DOM in-place.
4. **Mobile-friendly command bar.** The input must be usable on mobile keyboards (avoid tiny fonts, ensure proper viewport).
5. **LLM streaming is a must.** The command bar should show LLM responses as they stream in, not all at once.
6. **Accessibility basics.** The command bar needs an `<input>` with proper ARIA labels, role="combobox" pattern for autocomplete, and keyboard-only navigation.
7. **Build output goes to `web/dist/`** — the FastAPI server mounts this directory as static files.
8. **Do not use SvelteKit** — this is a SPA, not an SSR app. SvelteKit would add unnecessary complexity and bundle size.
