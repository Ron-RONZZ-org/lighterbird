# AGENTS.md — Root Project Rules for lighterbird

This is the canonical, repo-wide instruction file for AI agents working on **lighterbird**.

## Hierarchical Context Model

Agents **must** follow this rule:

> When working inside a directory, load the nearest `AGENTS.md` file and merge it with parent `AGENTS.md` files up to root.
> Local rules override global rules.

Context resolution order (highest priority first):
1. `AGENTS-[module].md` in module directories — module-specific context
2. `AGENTS.md` in current working directory (if present)
3. Root `AGENTS.md` — global project rules

---
## Project Overview

**lighterbird** is a command-driven personal information manager (PIM) integrating email, contacts, calendar, and todo into a single webapp with built-in BYOK (Bring Your Own Key) LLM support.

The interaction model is a **centralized command box** — type `!account add` to manage accounts, `!new` to see new emails, or just type naturally to chat with the built-in LLM. The philosophy: *you see only what you need* — no sidebars, no bloat.

The backend is forked from proven code in [A-lien](../A-lien) (email, contacts), [A-organizi](../A-organizi) (calendar, todo, journal), and [A-core](../A-core) (DB, crypto, keyring, AI providers). The frontend is a Svelte SPA served by a FastAPI Python server.

---

## Language and Naming Conventions

- **Source code**: English (variable names, comments, docstrings)
- **User-facing strings**: English first (i18n can be added later — unlike the A-ecosystem, lighterbird does not mandate Esperanto)
- **CLI command names**: English, **singular form** (`account`, `calendar`, `contact`, `todo`, `search`, `journal`, `letter`) — the `!` commands are user-facing. No plural command names (`!contacts` is legacy, use `!contact`).
- **URL paths, route names**: lowercase with hyphens (`/api/email/messages`)
- **Database columns**: English names throughout (e.g., `title`, `subject`, `created_at`, `email`). Migrated from the A-ecosystem's Esperanto convention in v0.3.0.

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend | Python 3.11+ | Ecosystem, existing A-ecosystem codebase |
| Backend framework | FastAPI + uvicorn | Lightweight, async, auto-docs |
| Frontend | Svelte 5 SPA | Minimal bundle, excellent custom component DX |
| Frontend build | Vite + svelte-spa-router | Fast dev, static export possible |
| Database | SQLite (WAL mode) | Embedded, zero-config, sufficient for single-user |
| Credential storage | System keyring (via `keyring` library) | Never store passwords in DB |
| AI providers | OpenAI-compatible API + Ollama | BYOK: bring your own model/key |
| Package manager | `uv` (development), `pip` (user install) | Fast, modern, reproducible |
| Build system | Hatchling | PEP 517 compliant, simple |
| Async HTTP | httpx | IMAP/SMTP use stdlib, calendar sync uses stdlib |

---

## Dependency Management

This project uses **uv** for development:

| Operation | Command |
|-----------|---------|
| Install project in dev mode | `uv pip install -e .` |
| Install dev deps | `uv pip install -e ".[dev]"` |
| Run tests | `uv run pytest tests/` |
| Add dependency | `uv add <pkg>` |
| Add dev dependency | `uv pip install <pkg>` |

**Exceptions:** README install instructions may use `pip` for users without `uv`. Runtime `install-on-confirmation` may fall back to `pip`.

---

## Source Tree Structure

```
lighterbird/
├── AGENTS.md                    # This file — global project rules
├── README.md
├── LICENSE                      # AGPL-3.0
├── pyproject.toml
├── .gitignore
├── src/
│   └── lighterbird/             # Main Python package
│       ├── __init__.py
│       ├── __main__.py          # python -m lighterbird entry point
│       ├── core/                # Forked from A-core: DB, crypto, keyring, AI, paths
│       ├── email/               # Forked from A-lien: IMAP, SMTP, contacts, accounts
│       ├── calendar/            # Forked from A-organizi: CalDAV, events, todo, journal
│       └── server/              # FastAPI web server: routes, middleware, static serving
├── tests/                       # Shared tests root
│   ├── test_core/
│   ├── test_email/
│   ├── test_calendar/
│   └── test_server/
├── core/                        # Module-level AGENTS-core.md lives here
│   └── AGENTS-core.md
├── email/                       # Module-level AGENTS-email.md lives here
│   └── AGENTS-email.md
├── calendar/                    # Module-level AGENTS-calendar.md lives here
│   └── AGENTS-calendar.md
├── letter/                      # Module-level AGENTS-letter.md lives here
│   └── AGENTS-letter.md
├── server/                      # Module-level AGENTS-server.md lives here
│   └── AGENTS-server.md
├── web/                         # Svelte frontend (separate Node project)
│   ├── AGENTS-web.md
│   ├── package.json
│   ├── vite.config.js
│   ├── svelte.config.js
│   └── src/
└── docs/                        # Documentation
```

---

## GUI + CLI Parity Requirement

**All functionalities MUST be accessible via BOTH GUI and CLI.** No feature may be CLI-only or GUI-only. This means:

- Every `!command` must have a corresponding GUI panel (form, tab, or overlay) accessible through the command bar or a toolbar button.
- Every GUI form/panel must have a corresponding `!command` accessible via the centralized command box.
- When adding a new feature, implement both the CLI handler (backend) and the GUI component (Svelte) simultaneously.
- The authoritative command metadata lives in `src/lighterbird/server/command/tree.py` (backend). The frontend fetches it on startup via `GET /api/v1/command/tree`. There is no hardcoded frontend tree — `commandTree.js` starts empty and is populated dynamically.

## Coding Guidelines

1. **No file > 500 lines.** Split by functional unit (follow A-ecosystem pattern).
2. **Type hints on all public functions.** Use `from __future__ import annotations`.
3. **Docstrings on all public functions.** Google-style or reStructuredText.
4. **Tests required for all modules.** `pytest` with `tmp_path` isolation for DB tests.
5. **SQLite in WAL mode.** Use `pragma journal_mode=wal` on connection.
6. **Passwords in system keyring only.** Never in SQLite, config files, or environment (beyond dev).
7. **Async where it matters.** FastAPI routes are async; IMAP/SMTP sync can be sync workers.
8. **Error messages include actionable suggestions.** "Set it with: `!account modify <uuid> --password <pw>`"
9. **Use `tr()` or `tr_multi()` for i18n** — but only once i18n infrastructure is in place. For initial development, plain English strings are acceptable.
10. **Missing CLI args → GUI redirect (default behaviour).** When a CLI command is invoked with missing required options and the command has an interactive form registered, the system shall redirect the user to the GUI with any already-specified options pre-filled. This is handled by the `_INTERACTIVE_FORMS` dict in `command.py` and the `form-required` response type. All interactive commands must be registered in `tree.py` (backend) with `interactive: true` — the frontend fetches this metadata dynamically.

## List Tab Standard Feature Set

All list tab components (`EmailListTab`, `JournalListTab`, `SieveListTab`, `ContactsListTab`, `TodoListTab`, `CalendarEventsListTab`) must implement the following standard feature set:

| Feature | Implementation |
|---------|---------------|
| **Selection mode** | Toggle via `V` key + toolbar "Select"/"Exit" button; checkboxes appear in reserved column |
| **Range selection** | Shift+click selects contiguous range; anchor point set on first click |
| **Keyboard navigation** | Arrow keys (up/down), PgUp/PgDn, Home/End, Space to toggle focused item |
| **"+ New" action** | `N` key (view mode) or toolbar "+ New" <kbd>N</kbd> button → opens add form |
| **Batch delete** | `Delete` key or toolbar button → ConfirmDialog → deletes all selected items |
| **UUID copy** | Click on truncated UUID (first 8 chars) → `navigator.clipboard.writeText()` → "Copied!" flash for 1.2s |
| **Email/address copy** | Click on email/from cell → copies address to clipboard (same flash pattern) |
| **Search** | `f` key toggles search bar; debounced 300ms with AbortController; min 2 chars |
| **Context-appropriate toolbar** | View mode: [Select] [hint] [+ New <kbd>N</kbd>]; Selection mode: [Exit] [count] [Delete]; Search mode: full-width search input |
| **Unsaved-changes guard** | Tab close → ConfirmDialog if form dirty; browser `beforeunload` if any dirty form exists; forms expose `dirty` derived rune + `onDirtyChange` callback |

### Shared Helpers

Common logic lives in `web/src/lib/listTabShared.svelte.js`:

| Export | Purpose |
|--------|---------|
| `createCopyState()` | Returns `copiedKey` (reactive) + `copyToClipboard(key)` — 1.2s auto-clear |
| `createSelectionManager(getItems, onOpen, onDeleteSelected, onRefresh, opts)` | Returns reactive selection state + keyboard navigation handler |
| `formatListItemDate(iso)` | Context-aware date formatting (today=time, this year=month+day, older=full) |
| `truncate(s, max)` | String truncation with ellipsis |
| `preview(s, max)` | First line, stripped of markdown, truncated |

### Response Type Mapping

Backend list commands return typed responses that map to frontend components:

| Command | Backend Response Type | Frontend Component |
|---------|----------------------|--------------------|
| `!email list` / `!email search` | `email-list` | EmailListTab |
| `!journal list` / `!journal search` | `journal-list` | JournalListTab |
| `!contacts list` / `!contacts search` | `contacts-list` | ContactsListTab |
| `!todo list` / `!todo search` | `todo-list` | TodoListTab |
| `!calendar list` / `!calendar event search` | `calendar-events` | CalendarEventsListTab |
| `!email sieve list` | `sieve-list` | SieveListTab |
| `!letter list` / `!letter search` | `letter-list` | LetterListTab |
| `!user info list` | `status` (profiles list) | DynamicForm / StatusPopup |

---

## Commit Message Format

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — new user-facing feature
- `fix:` — bug fix
- `docs:` — documentation only
- `chore:` — tooling, config, CI
- `test:` — test additions/fixes
- `refactor:` — code restructuring with no behavior change
- `web:` — frontend-only changes (Svelte)
- `server:` — backend API changes

---

## What to Avoid

- **Do not import from A-ecosystem packages at runtime.** lighterbird forks the code — all dependencies must be vendored under `src/lighterbird/`. The `../A-lien` references in README are for development reference only.
- **Do not duplicate logic across modules.** Each domain module (core, email, calendar) is self-contained. Shared utilities go in `core`.
- **Do not use `print()` for user output.** Use FastAPI structured responses or loguru/logging.
- **Do not store credentials in SQLite.** Keyring only.
- **Do not add heavy frameworks** (Django, SQLAlchemy, Celery) — this is a lightweight single-user app.
- **Do not hardcode paths.** Use `core.paths` module for XDG-compliant resolution.
- **Do not ship a full MTA/IMAP server.** lighterbird is a client, not a server.

---

## Module-Level AGENTS Files

The following module-specific AGENTS files are located in their respective directories:

| Module | AGENTS File | Description |
|--------|-------------|-------------|
| Core | `core/AGENTS-core.md` | DB, crypto, keyring, backup, AI providers, paths |
| Email | `email/AGENTS-email.md` | IMAP sync, SMTP send, contacts, accounts, Sieve |
| Calendar | `calendar/AGENTS-calendar.md` | CalDAV sync, events, todo, journal, labels |
| Letter | `letter/AGENTS-letter.md` | Paper letter management, PDF rendering, templates |
| Server | `server/AGENTS-server.md` | FastAPI routes, middleware, static serving |
| Web | `web/AGENTS-web.md` | Svelte SPA, command-bar UI, build tooling |

(Update this table as new modules are added)

---

## Dependency and Inheritance Map

```
Root AGENTS.md (global rules)
    │
    ├── core/AGENTS-core.md       DB, crypto, keyring, AI providers
    ├── email/AGENTS-email.md     IMAP, SMTP, contacts, accounts
    ├── calendar/AGENTS-calendar.md  CalDAV, events, todo, journal
    ├── letter/AGENTS-letter.md   Paper letters, PDF, templates
    ├── server/AGENTS-server.md   FastAPI backend, API routes
    └── web/AGENTS-web.md         Svelte SPA frontend
```

Local rules override global rules. Module-level files focus on domain-specific behavior, constraints, and invariants.
