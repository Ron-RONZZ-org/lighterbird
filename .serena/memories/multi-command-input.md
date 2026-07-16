# Multi-Command Input in ! Commands

## Proposal
Home page input box across lightercore + lighterbird + semantika accepts multiple `!` commands in one message:
`!email account modify ron@ronzz.org --redetect !email account modify hi@rongzhou.me --redetect`

Parsing: if 1st char is `!`, treat as commands. Each `!` starts a new command.

## Status
- [x] Reflection: aligned with project goals
- [x] GitHub issue filed: https://github.com/Ron-RONZZ-org/lighterbird/issues/190
- [x] Architect consulted
- [x] Issue updated with implementation plan

## Key Decisions
- **Parsing** → `lightercore/web/src/lib/multiCommand.js` (shared `@lightercore/ui` package)
- **Execution** → Sequential, continue-on-error
- **Results** → Multiple tabs (existing tabStore/popup patterns)
- **Interactive commands in batch** → Skip + error ("requires interactive form")
- **Cancellation** → AbortController + "Stop" button
- **Mixed `!` + `/*`** → Not supported in v1

## Files to change
- `lightercore/web/src/lib/multiCommand.js` (NEW) — splitCommands(), isMultiCommand()
- `lightercore/web/src/index.js` — export multiCommand
- `lighterbird/web/src/lib/HomeTab.svelte` — batch loop with skip/continue/abort
- `semantika/web/src/lib/HomeTab.svelte` — same change

## Edge Cases
- `!` inside quoted strings (`!todo add "urgent! fix bug"`) — NOT split (space check)
- ~150 lines total, no backend changes
