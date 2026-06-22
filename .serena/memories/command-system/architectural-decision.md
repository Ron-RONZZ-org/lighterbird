# Command System Redesign — Architectural Decision (2026-06-22)

## Issue
https://github.com/Ron-RONZZ-org/lighterbird/issues/3

## Research Sources
- A-lien (`../A-lien`): Typer-based CLI with `retposto konton ls` hierarchy, plugin entry points
- A-organizi (`../A-organizi`): Same Typer pattern, 5 sub-Typers (kalendaro, okazajo, todo, taglibro, etikedo)
- Current lighterbird: frontend-only JSON tree command dispatch, no backend endpoint

## Key Decisions
1. **Unified `!<domain> <action>` pattern** — all commands follow this, no more flat `!inbox`/`!new`/`!addevent`
2. **Backend `POST /api/v1/command`** — owns validation + dispatch; frontend only does autocomplete
3. **Simple decorator-based registry** (~30 lines Python) — no plugin system, no entry points
4. **Interactive forms** for multi-param commands (`!email send`, `!calendar event add`)
5. **LLM tool-calling** via same endpoint — LLM outputs `{tokens, flags}`

## Proposed Command Tree
```
!email list|read|send|search|sync|trash|archive
  account add|list|modify|remove
!calendar list
  event add|view|modify|remove|search
  account add|list|modify|remove|sync
!contacts list|add|view|modify|remove|search
!todo list|add|view|done|modify|remove|search
!journal list|write|view|search
!sync [--email] [--calendar]
!help [command]
```

## Implementation Roadmap (6 Phases)
1. Backend command endpoint + handlers for existing commands
2. Frontend simplification (strip apiMethod from tree, thin executor)
3. Command hierarchy restructure (new tree, backward compat aliases)
4. New domains (contacts, todo, journal)
5. Interactive forms (ComposeEmail.svelte, EventForm.svelte)
6. LLM integration (chat endpoint, tool calling)

## Files Created
`src/lighterbird/server/command/` (package), `server/routes/command.py`, `web/src/lib/commandExecutor.js`

## Open Questions
- `!sync` top-level vs per-domain? (Proposal: top-level with `--email`/`--calendar` flags)
- `!search` cross-domain vs per-domain? (Proposal: per-domain first)
- Interactive forms use same `/api/v1/command`? (Proposal: yes)
