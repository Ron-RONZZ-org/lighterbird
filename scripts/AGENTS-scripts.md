# AGENTS-scripts.md — Scripts Module Agent Instructions

## Summary

Dev tooling for lighterbird: seed data generation and the isolated dev server CLI.

Code lives in `src/lighterbird/scripts/`.

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Package init |
| `seed.py` | `seed_data_dir(target_dir, dot_dev_path)` — populates a directory with all 8 domain databases (email, calendar, contacts, todo, journal, letters, profiles, user_commands) + a demo prompt command file, containing test data from ``.dev`` credentials |
| `dev_cli.py` | `dev_main()` — CLI entry point registered as `lighterbird-dev` in `pyproject.toml` under `[project.scripts]` |
| `seed_spam_tokens.py` | Regenerates the Bayesian seed token table from the SpamAssassin public corpus. Run: ``uv run python src/scripts/seed_spam_tokens.py``. Outputs ``src/lighterbird/email/filters/spam_tokens.json``. |

## Usage

```bash
# Isolated dev server with seed data from .dev (auto-discovered from project root)
uv run lighterbird-dev --seed

# Isolated dev server with seed data from .prod (real credentials)
uv run lighterbird-dev --prod

# Isolated dev server without seed data
uv run lighterbird-dev

# Restore seed from a backup archive
uv run lighterbird-dev --seed-from path/to/backup.7z

# Persistent data directory (data survives restarts)
uv run lighterbird-dev --data-dir ~/lighterbird-data --prod

# Re-seed only on first run; subsequent starts skip seed
uv run lighterbird-dev --data-dir ~/lighterbird-data --seed

# Custom port
uv run lighterbird-dev --seed --port 9000
uv run lighterbird-dev --prod --port 9000

# Preserve the temp data directory after exit (for debugging)
uv run lighterbird-dev --seed --keep-data
uv run lighterbird-dev --prod --keep-data
```

## How It Works

`lighterbird-dev`:

1. Determines the data root:
   - **With `--data-dir <path>`**: uses the given persistent path (created if missing).
   - **Without `--data-dir`**: creates a temporary directory (`/tmp/lighterbird-dev-*/`).
2. Sets `LIGHTERBIRD_DATA_DIR`, `LIGHTERBIRD_CONFIG_DIR`, `LIGHTERBIRD_CACHE_DIR`, and `LIGHTERBIRD_STATE_DIR` to paths inside the data root.
3. If a seed source is given (`--seed`, `--prod`, or `--seed-from`), checks whether the data directory already has content. If it does, seeding is **skipped** (existing data preserved). If empty, seeding proceeds.
4. Starts uvicorn on the isolated databases.
5. On exit:
   - **`--data-dir`** paths are **never** cleaned up (data is persistent by intent).
   - **Temp directories** are removed (unless `--keep-data`).

The seeding step (when it runs) calls `seed_data_dir()` which:
   - Parses `.dev` or `.prod` for credentials (email, calendar, LLM API key)
   - Initializes all 8 domain databases with their schemas (using each domain's `get_db()` function)
   - Inserts seed data directly via SQL INSERT
   - Stores email and calendar passwords in the system keyring
   - Configures the LLM provider from `TEST_DEEPSEEK_APIKEY`

If `--seed-from <archive.7z>` is given instead, it extracts the 7z archive into the data directory using `lighterbird.core.backup._extract_archive()` before starting the server.

## Seed Data Generated

| DB | Content | Source |
|----|---------|--------|
| `email.db` | 1 account with auto-detected IMAP/SMTP | `.dev` |
| `calendar.db` | 1 calendar + 1 sample event | `.dev` |
| `contacts.db` | 1 contact | `test-contact.toml` or default |
| `todo.db` | 3 sample tasks (Buy milk, Review PR, Write docs) | hardcoded |
| `journal.db` | 1 sample entry | hardcoded |
| `letters.db` | 1 test letter | hardcoded |
| `profiles.db` | 1 user profile | `test-profile.toml` or default |
| `user_commands.db` | empty (schema ready) | — |

## Constraints

- **Keyring access is required** for seeded email/calendar accounts. If no system keyring is available, the seed script will fail when trying to store passwords (the `AccountService` raises `RuntimeError`).
- **The `.dev` file must exist** in the project root when using `--seed`, and the **`.prod` file** must exist when using `--prod`. They contain real credentials for IMAP, SMTP, and CalDAV servers.
- **Auto-detection of IMAP/SMTP servers** uses `email.server_detect.detect_servers()`, which performs MX lookups and provider pattern matching. This requires network access.
- **The temp directory is cleaned up on exit** unless `--keep-data` is passed.
- **With `--data-dir`, the directory is never cleaned up** — data persists across restarts. Seeding is skipped on subsequent runs if the directory already contains data.

## Testing with the Seeded Server

```bash
# Terminal 1
uv run lighterbird-dev --seed

# Terminal 2
node tests/playwright_e2e.mjs
node tests/e2e_comprehensive.mjs
```
