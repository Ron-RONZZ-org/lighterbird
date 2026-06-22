# AGENTS-core.md — Core Module Agent Instructions

## Summary

Foundation services forked from [A-core](../../A-core): database abstraction, cryptographic helpers, system keyring wrapper, backup/restore, LLM provider abstraction, path resolution, and i18n. All other lighterbird modules depend on this.

## Purpose and Expected Behavior

`src/lighterbird/core/` provides:

- **`db.py`** — SQLite wrapper (WAL mode, connection management, transaction helper)
- **`paths.py`** — XDG-compliant data/config/cache directory resolution
- **`keyring.py`** — System keyring abstraction (wraps `keyring` library, graceful fallback)
- **`crypto.py`** — AES-256-GCM encryption (PBKDF2 key derivation)
- **`backup.py`** — Timestamped, checksum-verified DB backups with retention pruning
- **`ai.py`** — LLM provider factory (`get_provider`)
- **`providers.py`** — OpenAI-compatible + Ollama provider implementations
- **`i18n.py`** — Multi-language string support (tr, tr_multi)
- **`exceptions.py`** — Centralized custom exception classes

## Constraints and Invariants

- **`keyring.py` must never raise on import** — the `keyring` library is optional; fall back to `None` if unavailable
- **`crypto.py` depends on `cryptography`** — this is a hard dependency (required in pyproject.toml)
- **All paths must go through `paths.py`** — never hardcode `~/.local/share/...`
- **Backup destination lives outside the module's data dir** — inside `~/.local/share/lighterbird/.backups/`
- **AI providers must never auto-execute** — the provider abstraction is stateless; execution gates belong in the server layer
- **API keys stored in system keyring only** — never in DB, config, or env (beyond dev convenience fallback)

## Input/Output Expectations

- `get_db()` returns a singleton SQLiteDB — WAL mode, foreign keys enabled
- `get_provider("openai")` returns an `OpenAICompatibleProvider` — env → .env → keyring auth resolution
- `get_provider("ollama")` returns an `OllamaProvider` — local-only, no auth needed
- `backup_database(path, module="lighterbird")` returns the backup path or `None`

## Documentation Reference

- [A-core AGENTS.md](../../A-core/AGENTS.md) — original source architecture
- [A-core crypto.py](../../A-core/src/A/core/crypto.py) — source of `crypto.py`
- [A-core keyring.py](../../A-core/src/A/core/keyring.py) — source of `keyring.py`
- [A-core backup.py](../../A-core/src/A/core/backup.py) — source of `backup.py`

## Domain-Specific Rules for Agents

1. **Fork, don't import.** Copy the needed code from A-core into `src/lighterbird/core/`. Strip A-core's plugin loader, registry, and CLI framework — lighterbird doesn't need them.
2. **Simplify aggressively.** Remove the `A-` prefix from all class/file names. Remove Esperanto CLI commands. Remove A-core's `CRUDService` base class if lighterbird uses a different pattern.
3. **Preserve security patterns.** The crypto and keyring modules should be modified as little as possible — they've been reviewed and hardened.
4. **AI provider abstraction stays stateless.** Providers are created on demand, not cached for the app lifetime. The server layer manages state (which provider is "active").
5. **Tests must use `tmp_path` isolation.** DB tests must never write to the real user data directory.
