# AGENTS-user-commands.md — User Commands Module Agent Instructions

## Summary

User-defined saved commands module for lighterbird. Provides CRUD for aliased command shortcuts with positional template expansion (e.g., `!mysearch` expands to `!email list --from $1 --after $2`).

## Purpose and Expected Behavior

`src/lighterbird/user_commands/` provides:

- **`db.py`** — `saved_commands` table schema (alias, template, description, created_at, updated_at)
- **`service.py`** — `UserCommandsService`: CRUD for saved commands, template expansion with `$1`–`$9` positional arguments

## Constraints and Invariants

- **Aliases must be unique** — case-insensitive uniqueness enforced at the DB level
- **Template expansion is positional** — `$1`, `$2`, … `$9` are replaced in order by user-provided arguments
- **No recursive expansion** — a saved command cannot reference another saved command (prevents infinite loops)
- **Character limit on aliases** — max 50 characters, lowercase alphanumeric + hyphens recommended
- **Character limit on templates** — max 2000 characters
- **Templates are plain command strings** — no scripting, no shell execution. They expand into `!` commands that are parsed by the command engine

## Input/Output Expectations

- `!user saved-commands list` returns `{"type": "status", ...}` with all saved commands
- `!user saved-commands add` opens a form (interactive) — rendered by `SavedCommandsTab`
- `!user saved-commands remove <alias>` deletes a saved command
- When a user types `!<alias>`, the command engine resolves it via `UserCommandsService.expand(alias, args)` before dispatching
- `expand(alias, args)` returns `(expanded_template, remaining_args)` tuple

## Documentation Reference

- Command system (`server/command/`) — the parser and router that dispatches expanded commands
- [A-lien AGENTS.md](../../A-lien/AGENTS.md) — original precedent for user commands (A-lien's `KonservitajKomandoj`)

## Domain-Specific Rules for Agents

1. **No Esperanto aliases.** Unlike A-lien's `konservitaj_komandoj`, lighterbird uses English aliases throughout.
2. **Singleton service.** `UserCommandsService` does not extend `CRUDService` — it's a standalone service with direct SQL queries. Keep it consistent with the `EmailAccountService` pattern.
3. **Template expansion happens before dispatch.** The command engine intercepts any `!<word>` where `<word>` matches a saved command alias, expands the template with positional args, and re-dispatches the expanded command.
4. **Keep it simple.** No nested expansion, no conditionals, no loops. Templates are simple command strings with positional placeholders.
5. **Error on unknown alias.** If a user types `!unknown_alias` that doesn't match any saved command or built-in command, return a clear error with available aliases.
