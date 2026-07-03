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
| Run isolated dev server | `uv run lighterbird-dev --seed` |
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
│       ├── scripts/             # Dev tooling: seed data generator, dev CLI
│       │   ├── __init__.py
│       │   ├── dev_cli.py       # lighterbird-dev CLI entry point
│       │   └── seed.py          # Seed data generator for test databases
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

## Testing Requirements

### GUI + Incomplete CLI → GUI Form Testing

**All interactive commands MUST be tested via BOTH the API and the browser GUI.** Incomplete CLI commands that trigger a form popup (`form-required` response) are the primary UX pattern and must be explicitly verified end-to-end:

1. **Test incomplete commands that trigger form popups** — for every command with `interactive: true` in `tree.py`:
   - Type the command with missing required params (e.g. `!user info add` without a profile name)
   - Verify the GUI opens the correct form with all fields visible
   - Verify the form title matches the command
   - Verify the "Save" button submits correctly
   - Verify the result tab shows success

2. **Test the frontend interception (`shouldIntercept` in `commandRouter.js`)** — for every `add`/`write` command:
   - Verify `resolveAddFormType()` has a mapping for the command path
   - Verify `resolveListIdKey()` has a mapping for the list command path
   - Verify `resolveAddTitle()` has a title for the form type
   - Verify `_inferCommandPath()` in `FormTab.svelte` has the form type → command path mapping
   - If any of these mappings are missing, the form shows "Unknown form type" instead of the correct form.

3. **The authoritative list of mappings to check** — when adding a new interactive command, update ALL of these:
   - `_INTERACTIVE_FORMS` in `server/routes/command.py` (backend)
   - `resolveAddFormType()` in `web/src/lib/commandRouter.js`
   - `resolveListIdKey()` in `web/src/lib/commandRouter.js`
   - `resolveAddTitle()` in `web/src/lib/commandRouter.js`
   - `_inferCommandPath()` in `web/src/lib/FormTab.svelte`
   - `detectPersistentType()` in `web/src/App.svelte` and `web/src/lib/HomeTab.svelte`

4. **GUI tests use headless Playwright — ALWAYS prefer E2E scripts over the interactive browser tool.**
   - **One-time setup**: Ensure Playwright's Chromium is installed before running E2E tests:
     ```bash
     cd web && npx playwright install chromium
     ```
     Without this, the E2E fixture fails with "No Chromium browser found". The download is ~300MB and takes ~90s.
   - **Run the E2E test scripts (`node tests/e2e_comprehensive.mjs`, `node tests/playwright_e2e.mjs`)** as the primary verification method. These are fast, reliable, and catch regressions automatically.
   - **Use the `browser` tool (headed mode) ONLY as a last resort** when an E2E script cannot reproduce the issue and you need to manually inspect the UI. Headed mode sessions are fragile: tool calls are interrupted if the user types "continue" while an action is in-flight, leaving the browser in an inconsistent state.
   - Always use `http://127.0.0.1:<port>` for local dev servers (IPv4, not `localhost` which can resolve to IPv6 `::1`).
   - **Timeout**: E2E tests take ~2 minutes. When running via the shell tool, set a timeout of at least 300s (`timeout: 300000`).

5. **Use `lighterbird-dev --seed` for isolated E2E testing** — instead of starting the production server, use the isolated dev server which creates a temporary data directory and seeds it with test data from ``.dev``:

   ```bash
   # Terminal 1: start isolated seeded server
   uv run lighterbird-dev --seed

   # Terminal 2: run Playwright E2E tests
   # (one-time setup: cd web && npx playwright install chromium)
   node tests/playwright_e2e.mjs
   node tests/e2e_comprehensive.mjs
   ```

   The seeded data includes an email account (from ``.dev`` credentials with auto-detected IMAP/SMTP), a calendar account with a sample event, a test contact, sample todos, a journal entry, and a user profile. See ``scripts/AGENTS-scripts.md`` for details.

6. **Cowriting via GUI** — test LLM co-writing through form editors (ComposeEmail, TodoAddForm, JournalWrite) by filling in text and invoking the cowrite feature. Also test via the cowrite API directly (`POST /api/v1/cowrite`).

### E2E Test Automation

Playwright E2E tests are integrated into pytest via the ``--e2e`` flag:

| Command | Behavior |
|---------|----------|
| `uv run pytest tests/` | Unit tests only (203 tests, E2E skipped) |
| `uv run pytest --e2e tests/test_e2e.py` | E2E tests only (auto-starts seeded server) |
| `uv run pytest --e2e --keep-e2e-data` | E2E + preserve temp data for debugging |

**Prerequisite**: Playwright's Chromium must be installed:
```bash
cd web && npx playwright install chromium
```

The ``conftest.py`` defines a session-scoped ``e2e_server`` fixture that:
1. Allocates a free TCP port (no port conflicts)
2. Creates a temp data directory and seeds it
3. Starts uvicorn as a subprocess
4. Health-checks before proceeding (15s timeout)
5. Yields URL + Chromium path to the test
6. Terminates server + cleans up temp dir on teardown

Existing ``.mjs`` scripts (``tests/playwright_e2e.mjs``, ``tests/e2e_comprehensive.mjs``) are wrapped by ``tests/test_e2e.py`` via ``subprocess.run()`` — no script rewrite needed.

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
| **Keyboard navigation** | Arrow keys (up/down), PgUp/PgDn, Home/End, Space to toggle focused item, `T` key to toggle tree/flat view (todo only) |
| **"+ New" action** | `N` key (view mode) or toolbar "+ New" <kbd>N</kbd> button → opens add form |
| **Batch delete** | `Delete` key or toolbar button → ConfirmDialog → deletes all selected items |
| **UUID copy** | Click on truncated UUID (first 8 chars) → `navigator.clipboard.writeText()` → "Copied!" flash for 1.2s |
| **Email/address copy** | Click on email/from cell → copies address to clipboard (same flash pattern) |
| **Search** | `f` key toggles search bar; debounced 300ms with AbortController; min 2 chars |
| **Tags display** | Colored tag pills rendered inline in the row; batch-fetched via junction table |
| **Sort dropdown** | `sort` param sent to backend; options: created, priority, due, title |
| **Mode toggle** | `T` key or tree/flat toggle button re-queries backend with opposite mode |
| **Context-appropriate toolbar** | View mode: [Select] [hint] [+ New <kbd>N</kbd>]; Selection mode: [Exit] [count] [Delete]; Search mode: full-width search input |
| **Unsaved-changes guard** | Tab close → ConfirmDialog if form dirty; browser `beforeunload` if any dirty form exists; forms expose `dirty` derived rune + `onDirtyChange` callback |

### Shared Export/Import Components

Export and import use two shared dialog components:

| Component | Props | Purpose |
|-----------|-------|---------|
| `ExportDialog.svelte` | `domain`, `items`, `format`, `fileName`, `onClose` | Trigger download of selected items in the appropriate format |
| `ImportDialog.svelte` | `domain`, `acceptedFormats`, `onImport`, `onClose` | File picker + upload for importing items from standard formats |

Backend format conversion lives in domain services (not a unified `export/` module). A shared YAML frontmatter utility exists in `core/yaml_frontmatter.py` for `.md` export/import across todo, journal, and letter domains.

### Shared Helpers

Common logic lives in `web/src/lib/listTabShared.svelte.js`:

| Export | Purpose |
|--------|---------|
| `createCopyState()` | Returns `copiedKey` (reactive) + `copyToClipboard(key)` — 1.2s auto-clear |
| `createSelectionManager(getItems, onOpen, onDeleteSelected, onRefresh, opts)` | Returns reactive selection state + keyboard navigation handler |
| `formatListItemDate(iso)` | Context-aware date formatting (today=time, this year=month+day, older=full) |
| `truncate(s, max)` | String truncation with ellipsis |
| `preview(s, max)` | First line, stripped of markdown, truncated |

### Shared Form Components

Reusable components for form inputs live in `web/src/lib/`:

| Component | Purpose |
|-----------|---------|
| `FormField.svelte` | Unified form field wrapper (label, hint, error, required badge) |
| `MultiEntryField.svelte` | Chip-based multi-value input with autocomplete; props: `label`, `entries` (Svelte 5 `$bindable` array), `autocompleteQuery`, `placeholder`, `hint`, `allowDuplicates`, `maxEntries`, `onDirtyChange` |
| | Used by: ComposeEmail (cc, bcc), TodoAddForm (dependency, tags), LetterForm (tags), LetterListTab (tag filter) |
| | Behavior: ENTER adds chip, X removes, double-click edits, Backspace on empty removes last |

### Response Type Mapping

Backend list commands return typed responses that map to frontend components:

| Command | Backend Response Type | Frontend Component |
|---------|----------------------|--------------------|
| `!email list` / `!email search` | `email-list` | EmailListTab |
| `!email export eml <uuid>` | download .eml | ExportDialog / direct download |
| `!email import eml <path>` | `status` | ImportDialog |
| `!journal list` / `!journal search` | `journal-list` | JournalListTab |
| `!journal export md <uuid>` | `status` (markdown) | ExportDialog |
| `!journal import md <path>` | `status` | ImportDialog |
| `!contacts list` / `!contacts search` | `contacts-list` | ContactsListTab |
| `!contact export vcf <uuid>` | `status` (vcf) | ExportDialog |
| `!contact import vcf <path>` | `status` | ImportDialog |
| `!todo list` / `!todo tree` / `!todo search` | `todo-list` | TodoListTab (tree/flat toggle, tags filter, sort) |
| `!todo export md <uuid>` | download .md | ExportDialog |
| `!todo import md <path>` | `status` | ImportDialog |
| `!calendar list` / `!calendar event search` | `calendar-events` | CalendarEventsListTab |
| `!calendar event export ics <uuid>` | `status` (ics) | ExportDialog |
| `!calendar event import ics <path>` | `status` | ImportDialog |
| `!email sieve list` | `sieve-list` | SieveListTab |
| `!letter list` / `!letter search` | `letter-list` | LetterListTab |
| `!letter export md <uuid>` / `!letter export pdf <uuid>` | `status` (md/pdf) | ExportDialog |
| `!letter import md <path>` | `status` | ImportDialog |
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
| Scripts | `scripts/AGENTS-scripts.md` | Dev CLI, seed data generator, test infrastructure |
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
    ├── scripts/AGENTS-scripts.md Dev CLI, seed data, test infra
    ├── server/AGENTS-server.md   FastAPI backend, API routes
    └── web/AGENTS-web.md         Svelte SPA frontend
```

Local rules override global rules. Module-level files focus on domain-specific behavior, constraints, and invariants.
