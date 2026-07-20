# lighterbird

Lighterbird — email, contacts, calendar, todo, journal, and paper letters. A command-driven personal information manager (PIM) with built-in BYOK (Bring Your Own Key) LLM support. AGPL-3.0.

## Three Interaction Worlds

The command bar accepts three input types — **CLI** (`!commands`), **prompt templates** (`/*commands`), and **natural language** (plain text → LLM). Each operation benefits from whichever interface suits it best:

| Interface | Best for | Example |
|-----------|----------|---------|
| **CLI** (`!`) | Batch ops, simple mutations, deterministic commands | `!email block add @spamdomain` |
| **GUI** (click) | Browsing, complex forms, visual context | Reading email threads, calendar grid |
| **LLM** (text) | Fuzzy recall, multi-step, natural language | "Show me emails from John last week" |

## Quick examples

- `!account add/list/modify/remove` — manage accounts
- `!email` / `!todo` / `!calendar` / `!contact` / `!journal` — open domain list view
- `!todo add --tags work,urgent` — tag your todos; filter with `!todo list --tags work`
- `!email block add @spamdomain` — block a domain (hard Sieve reject)
- `!email spam stats` — show Bayesian classifier and phishing feed statistics
- `!email send --help` — see all flags and params in autocomplete
- `!email/!todo/!journal/!contact/!calendar/!letter export` — export items as .eml, .ics, .vcf, .md
- `!email/!todo/!journal/!contact/!calendar/!letter import` — import items from standard file formats
- `!reset <path.7z>` — backup all data to a 7z archive, then reset to a fresh state
- `!reset --no-backup` — reset WITHOUT backup (requires GUI confirmation)
- **Multi-command input** — chain multiple `!` commands in one message
- Just type naturally → ask the built-in LLM to do things on your behalf
- As-you-type command suggestions with UUID/entity completion — no memorisation needed

## Spam & Phishing Detection

Three-tier protection accessible from the email view toolbar:

| Button | Action | Mechanism |
|--------|--------|-----------|
| 🔴 **Block** (From row) | Hard reject via Sieve | Existing `!email block add` — blocks sender or domain entirely |
| 🟡 **Spam** (From row) | Soft classification + move to \Spam | Bayesian token filter (chi-squared) trains on content; pre-baked seed table gives ~80% Day-1 accuracy |
| 🟠 **Fraudulent** (From row) | Hard-delete + watchlist | Phishing feed integration (OpenPhish/PhishTank/PhishStats) + display-name spoof detection; does NOT train Bayesian model to avoid false positives on brand names |

Marking messages as spam trains a per-user Bayesian token model. The CLI provides `!email spam stats` for classifier statistics. Reporting spam/fraud is done via the GUI buttons or LLM natural language (UUIDs are not CLI-friendly).

## Architecture

```
lighterbird/
├── core/              Forked from A-core      — DB, crypto, keyring, AI providers, paths
├── email/             Forked from A-lien      — IMAP sync, SMTP send, accounts, Sieve
│   └── filters/
│       ├── spam.py         — Blocklist CRUD (hard block via Sieve reject)
│       ├── spam_detect.py  — Bayesian classifier (chi-squared, token training)
│       └── phishing.py     — Phishing feed integration + display-name spoof detection
├── calendar/          Forked from A-organizi  — CalDAV, events
├── contacts/          Extracted from email    — Contact CRUD, VCF import/export
├── journal/           Extracted from calendar — Journal entries, labels
├── todo/              Extracted from calendar — Tasks, priorities, subtasks, dependencies
├── profiles/          New module              — User identity profiles
├── user_commands/     New module              — Saved command aliases with templates
├── letter/            New module              — Paper letter management, PDF rendering
├── reset/             New module              — Reset with backup and reinitialisation
├── server/            FastAPI backend         — REST API, command system, static serving
└── web/               Svelte 5 SPA            — Command-bar UI, rich result rendering
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

### Customising the LLM

User-editable config files are auto-created on first server start:

- **`~/.config/lighterbird/system_prompt.md`** — the LLM agent's system prompt.
  Edit to change how the AI behaves (tone, rules, constraints).
- **`~/.config/lighterbird/cowrite_style.md`** — co-writing style guide (general).
  Cross-cutting rules: tone, language, active voice.
- **`~/.config/lighterbird/cowrite_style_email.md`** — email-specific style.
- **`~/.config/lighterbird/cowrite_style_journal.md`** — journal-specific style.
- **`~/.config/lighterbird/cowrite_style_todo.md`** — todo-specific style.
- **`~/.config/lighterbird/cowrite_style_letter.md`** — letter-specific style.

Co-writing uses a **cascade model**: the general style (`cowrite_style.md`) is
always loaded first, and the domain-specific file is appended under a
``## Domain-specific Guide`` heading when you trigger co-writing for that
domain (e.g. composing an email loads ``cowrite_style.md`` +
``cowrite_style_email.md``).

All files are seeded with sensible defaults and can be edited freely.
Changes take effect on the next co-writing request (no server restart needed
for the system prompt — call ``POST /api/v1/llm/reload-prompt`` to apply
immediately).

### Disable file watching

To run the Vite dev server without file watching or HMR (useful when you want manual refresh on restart):

```bash
DISABLE_WATCH=true npm run dev
```

This sets `server.watch: null` and `server.hmr: false` — no chokidar watcher runs and no WebSocket connection is established. Restart the process to see changes.

## Testing

### Unit Tests (pytest)

```bash
uv run pytest tests/ -m "not e2e"
```

This runs all backend tests (currently **207+**). E2E tests are automatically skipped.

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

Available E2E test scripts:

| Script | Description | Timeout |
|--------|-------------|---------|
| `playwright_e2e.mjs` | Quick smoke tests (account CRUD, tab completion, !help) | 120s |
| `e2e_comprehensive.mjs` | Full suite (list, create, search, backup, sync, tab nav, LLM) | 180s |
| `e2e_gui_smoke.mjs` | GUI smoke tests: DOM rendering, tab navigation, form popups | 180s |
| `e2e_full.mjs` | Full coverage: every registered command, CRUD, search, export/import | 420s |
| `e2e_email_spam_buttons.mjs` | Block/Spam buttons in email view, ConfirmDialog interaction | 120s |

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
- Spam detection schema (``spam_user_tokens``, ``phishing_feeds``, ``phishing_domains``, ``spam_feedback`` tables)
- Pre-baked Bayesian seed table (``spam_tokens.json``) for Day-1 spam classification

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
