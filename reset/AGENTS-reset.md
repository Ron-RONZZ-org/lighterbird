# AGENTS-reset.md — Reset Module

## Purpose

The `reset/` module provides the ability to reset lighterbird to a fresh state, optionally creating a backup 7z archive first.

## Dependencies

- `core/backup.py` — 7z archive creation (``_create_strategy_archive()``, ``_checkpoint_known_dbs()``)
- `core/keyring.py` — ``delete_password()`` for clearing stored credentials
- `core/paths.py` — ``ensure_dirs()``, ``protect_directory()`` for data directory management
- `server/deps.py` — ``reset_services()`` for closing all active DB connections

## Key Functions

### `reset_to_fresh_state(backup_path=None)`

Located in `core/reset.py`. The six-step process:

1. **Collect known accounts** — reads existing `email.db` and `calendar.db` for emails/calendar UUIDs (needed for keyring cleanup before files are deleted)
2. **Create backup** — if ``backup_path`` is provided, checkpoints all DBs and creates a 7z archive at the given path
3. **Close connections** — calls ``reset_services()`` to close all DB connections
4. **Delete databases** — removes all ``*.db`` files from ``data_dir()``
5. **Clear keyring** — removes known password entries for `lighterbird-llm`, `lighterbird/email/*`, and `lighterbird/calendar/*`
6. **Recreate schemas** — calls each module's ``get_db()`` (which runs ``CREATE TABLE IF NOT EXISTS``) to initialise empty databases
7. **Re-protect directories** — runs ``ensure_dirs()`` to recreate sentinel files

## Command

The `!reset` command is a top-level command (not nested under `!backup`):

| Syntax | Description |
|--------|-------------|
| `!reset <path.7z>` | Backup to path, then reset |
| `!reset --no-backup` | Reset without backup (returns `form-required` → GUI ConfirmDialog) |

## Frontend Integration

- `--no-backup` mode returns `form-required` with form type `reset-no-backup`
- `App.svelte` and `HomeTab.svelte` intercept `form === "reset-no-backup"` and show `ConfirmDialog`
- User confirms → frontend sends `confirmed: "true"` flag to proceed
- `ConfirmDialog.svelte` supports `title`, `confirmText`, `variant` props (added in this module)

## Constraints

- `path` and `--no-backup` are mutually exclusive — both triggers a validation error
- `--no-backup` without `confirmed` always returns form-required (no CLI bypass)
- Config files in `config_dir()` are NOT deleted (user keeps custom prompts/backup strategies)
- Keyring entries are best-effort: only known entries (from DBs before deletion) are cleared
- Server continues running after reset — no restart needed
