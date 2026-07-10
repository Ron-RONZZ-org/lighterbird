# lighterbird

Lighterbird — email, contacts, calendar, todo, journal, and paper letters. A command-driven personal information manager (PIM) with built-in BYOK (Bring Your Own Key) LLM support. AGPL-3.0.

## Philosophy: You see only what you need

Traditional PIM apps drown you in sidebars, nested menus, and feature flags. Lighterbird does the opposite:

```
┌──────────────────────────────────────┐
│ ❯ !account add ...                   │  ← Always-visible command bar
├──────────────────────────────────────┤
│                                      │
│  Rich result area                    │  ← Shows only what you asked for
│  (email reader, calendar grid,       │
│   todo list, LLM chat, etc.)         │
│                                      │
└──────────────────────────────────────┘
```

- `!account add/list/modify/remove` — manage accounts
- `!email` / `!todo` / `!calendar` / `!contact` / `!journal` — open domain list view (root command defaults to list)
- `!todo add --tags work,urgent` — tag your todos; filter with `!todo list --tags work`
- `!todo list --mode tree` — toggle between flat and tree view
- `!todo list --sort priority` — sort by priority, due date, or title
- `!email send --help` — see all flags and params in autocomplete
- `!email/!todo/!journal/!contact/!calendar/!letter export` — export items as .eml, .ics, .vcf, .md
- `!email/!todo/!journal/!contact/!calendar/!letter import` — import items from standard file formats
- `!reset <path.7z>` — backup all data to a 7z archive, then reset to a fresh state
- `!reset --no-backup` — reset WITHOUT backup (requires GUI confirmation)
- Just type naturally → ask the built-in LLM to do things on your behalf
- As-you-type command suggestions with UUID/entity completion — no memorisation needed

## Architecture

```
lighterbird/
├── core/          Forked from A-core       — DB, crypto, keyring, AI providers, paths
├── email/         Forked from A-lien       — IMAP sync, SMTP send, accounts, Sieve
├── calendar/      Forked from A-organizi   — CalDAV, events
├── contacts/      Extracted from email     — Contact CRUD, VCF import/export
├── journal/       Extracted from calendar  — Journal entries, labels
├── todo/          Extracted from calendar  — Tasks, priorities, subtasks, dependencies
├── profiles/      New module              — User identity profiles
├── user_commands/ New module              — Saved command aliases with templates
├── letter/        New module              — Paper letter management, PDF rendering
├── reset/         New module              — Reset with backup and reinitialisation
├── server/        FastAPI backend          — REST API, command system, static serving
└── web/           Svelte 5 SPA             — Command-bar UI, rich result rendering
```

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | Python 3.11+ / FastAPI | Lightweight, async, auto-docs |
| Frontend | Svelte 5 SPA + Vite | Minimal bundle, excellent custom component DX |
| Database | SQLite (WAL mode) | Embedded, zero-config |
| Credentials | System keyring | Never in DB or config files |
| AI | OpenAI-compatible API + Ollama | BYOK: bring your own model/key |

## Quick Start

```bash
# Backend
uv pip install -e .
uv run python -m lighterbird

# Frontend (separate terminal)
cd web
npm install
npm run dev
```

> **Note**: `python -m lighterbird` starts the **production** server using the real XDG data
> directory (``~/.local/share/lighterbird/``). For an isolated temp instance with test data,
> use ``lighterbird-dev --seed`` instead (see [Development Server](#development-server)).

Open http://localhost:6005 — the Vite dev server proxies API calls to the Python backend (default port 6006).

**Custom backend port**: Set `LIGHTERBIRD_PORT` to run the backend on a different port:

```bash
# Terminal 1: backend on custom port
LIGHTERBIRD_PORT=8764 uv run python -m lighterbird

# Terminal 2: Vite frontend auto-detects the same port
LIGHTERBIRD_PORT=8764 npm run dev
```

The `lighterbird-dev` CLI also respects `LIGHTERBIRD_PORT`. The `--port` CLI flag takes precedence over the env var (CLI > env > 6006). In production (built SPA served by FastAPI), port configuration is automatic — everything runs on the same origin, no proxy needed.

## Testing

### Unit Tests (pytest)

```bash
uv run pytest tests/ -m "not e2e"
```

This runs all backend tests (currently **225**). E2E tests are automatically skipped.

### E2E Browser Tests (Playwright)

E2E tests simulate real user interactions in a headless Chromium browser. They require:

1. Playwright Node dependencies installed:
   ```bash
   cd web && npm ci && npx playwright install chromium
   ```
2. The Svelte frontend built:
   ```bash
   cd web && npm run build
   ```

Run via pytest (auto-starts seeded server on a dynamic port):

```bash
uv run pytest tests/test_e2e.py --e2e -v
```

To preserve the temporary data directory for debugging after a failure:

```bash
uv run pytest tests/test_e2e.py --e2e --keep-e2e-data -v
```

The pytest fixture automatically:
- Allocates a free TCP port
- Seeds databases with test data
- Starts the uvicorn server
- Runs the Playwright scripts
- Tears down both server and temp data on completion

## Dependencies

lighterbird depends on [lightercore](../lightercore) for shared infrastructure (DB, paths, exceptions, CRUD, backup). When setting up a development environment, clone both repos side by side:

```bash
git clone https://github.com/Ron-RONZZ-org/lighterbird.git
git clone https://github.com/Ron-RONZZ-org/lightercore.git
cd lighterbird
uv pip install -e "../lightercore" -e ".[dev]"
```

## Development Server

For E2E testing or isolated development, use the `lighterbird-dev` CLI. It creates a temporary data directory, optionally seeds it with test credentials, and starts the server. The port can be set via `--port` or the `LIGHTERBIRD_PORT` environment variable:

```bash
# Start with seed data from .dev (test credentials)
uv run lighterbird-dev --seed

# Start with seed data from .prod (your real credentials)
uv run lighterbird-dev --prod

# Start with clean temp database (no seed)
uv run lighterbird-dev

# Start with persistent data directory (data survives restarts)
uv run lighterbird-dev --data-dir ~/lighterbird-data --prod

# Start with persistent dir, reseed from .dev if empty
uv run lighterbird-dev --data-dir ~/lighterbird-data --seed

# Preserve the temp data directory after exit (for debugging)
uv run lighterbird-dev --seed --keep-data

# Suppress info output (errors still shown)
uv run lighterbird-dev --seed --quiet
```

The seed data includes:
- Email accounts with auto-detected IMAP/SMTP servers
- A calendar account with a sample event
- A test contact (from ``test-contact.toml`` if present)
- Sample todos, journal entry, and letter
- A user profile (from ``test-profile.toml`` if present)

Use ``--seed-from <archive.7z>`` to restore from a backup archive. For persistent development, use ``--data-dir <path>`` instead of the default temp directory — data inside the directory will survive server restarts.

Both ``.dev`` and ``.prod`` files use the same ``KEY="VALUE"`` format and are placed in the project root. The ``.prod`` file is gitignored — it's intended for your real credentials, while ``.dev`` holds shared test credentials for CI or teammate use.

### First sync performance

The first sync fetches message headers for all folders (body text and attachments are downloaded on demand when you open a message). For an account with 30 folders and ~1,850 messages the first sync takes ~95 seconds over a typical broadband connection. Subsequent syncs are much faster — ~7 seconds — because folders with no new messages are skipped via CONDSTORE (RFC 4551).

| Metric | First sync | Subsequent syncs |
|--------|-----------|-----------------|
| Folders | 31 (30 server + 1 seed) | 31 |
| Messages | 1,849 header-only | ~19 new |
| Time | ~95s | ~7s |
| Body download | On-demand only | On-demand only |

The first sync is slower because every folder must be scanned for UIDs and every new message's header must be downloaded. On subsequent runs, CONDSTORE skips folders whose modification sequence number hasn't changed, eliminating SELECT/SEARCH/FETCH round-trips for folders with no new activity.

## Status

**Pre-alpha.** The code is forked from [A-lien](../A-lien), [A-organizi](../A-organizi), and [A-core](../A-core), with modules extracted into standalone domains (contacts, todo, journal, profiles, letter, user_commands). Backend logic is proven; frontend is feature-complete for most domains.
