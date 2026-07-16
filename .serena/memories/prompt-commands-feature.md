# Feature: File-Based Prompt Commands (`/*` prefix)

## Summary
Feature request #132 on lighterbird: File-based LLM prompt commands in `~/.config/lighterbird/commands/*.md`, invoked via `/*` prefix. Inspired by OpenCode commands but simpler: no YAML frontmatter, single-agent, no LLM tool awareness.

## Key Design Decisions (from @architect review)
- **What they are**: Saved LLM prompt templates with `$1..$9` + `$ARGUMENTS` substitution
- **What they are NOT**: NOT `!command` templates (that's what `user_commands` does), NOT LLM tool definitions
- **Prefix**: `/*` (distinct from `!`)
- **Storage**: Filesystem `.md` files (no DB, no CRUD)
- **Expansion/Execution**: Backend only (frontend cannot read filesystem)
- **lightercore module**: `prompt_commands.py` — `PromptCommand` dataclass, scanner, loader, expander
- **LLM awareness**: None — commands are user-side shortcuts only

## API Surface
- `GET /api/v1/prompt-commands/list` — autocomplete source
- `POST /api/v1/prompt-commands/expand` — preview expanded text
- `POST /api/v1/prompt-commands/execute` — execute (load → expand → LLM → SSE stream)

## Implementation Phases
1. **MVP**: lightercore module → backend API → frontend routing
2. **Autocomplete**: virtual `/*` tree in commandTree.js + suggestions
3. **Polish**: error handling, seed data, hot-reload

## Related Files
- `lightercore/src/lightercore/prompt_commands.py` (new)
- `lighterbird/src/lighterbird/server/routes/prompt_commands.py` (new)
- `lighterbird/web/src/lib/parser.js` (modify)
- `lighterbird/web/src/lib/commandExecutor.js` (modify)
- `lighterbird/web/src/lib/CommandBar.svelte` (modify)
