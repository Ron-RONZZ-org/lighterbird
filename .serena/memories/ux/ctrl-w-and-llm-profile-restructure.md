# Ctrl+W + Unified !llm profile — Implementation Summary

**Issue:** #6
**Commit:** 7c01777
**Date:** 2026-06-23

## Changes

### Ctrl+W tab closing
File: `web/src/lib/TabView.svelte`
- Ctrl+W/Cmd+W closes current closable tab (same logic as Escape)
- If only home tab remains, shows `confirm("Close lighterbird?")` — user confirms lets browser close, cancels prevents default
- Handles focus-in-input gracefully: Ctrl+W has no standard text-editing behavior, so it's handled globally

### Unified `!llm profile` command group
File: `src/lighterbird/server/command/handlers/llm.py`

New command space (no backward compat aliases — pre-release):

| Command | Action |
|---------|--------|
| `!llm profile show` | Returns `{"_summary": "done"}` |
| `!llm profile new <type>` | Create config from scratch (was `!llm configure`) |
| `!llm profile set --flag` | Modify current settings (new — all flags optional, merges with current) |
| `!llm profile clear` | Clear config (was `!llm reset`) |
| `!llm profile save <name>` | Save current as named profile (was `!llm profile add`) |
| `!llm profile load <name>` | Load saved profile (was `!llm profile switch`) |
| `!llm profile list` | List saved profiles (unchanged behavior) |
| `!llm profile delete <name>` | Delete profile (was `!llm profile remove`) |
| `!llm prompt` | Show system prompt (unchanged) |
| `!llm <name>` | Quick-switch to profile (unchanged) |

### Frontend autocomplete
File: `web/src/lib/commandTree.js`
- LLM section rebuilt with new subcommand structure
- `configure`, `config`, `reset` nodes removed
- `profile > show/new/set/clear/save/load/list/delete` nodes added

## Key decisions
- **No backward-compat aliases** — pre-release, breaking changes acceptable
- **!llm profile** is the single concept: your current setup IS the active profile
- `!llm profile set` uses `flags.get(key, current_value)` pattern to merge partial updates
