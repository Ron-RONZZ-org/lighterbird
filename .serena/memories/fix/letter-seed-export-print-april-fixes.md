# Fix: Letter seed body, export-md raw markdown, Ctrl+P print behavior

## Date
2026-07-03

## Bugs Fixed

### Bug 1: Letter body not stored during seeding (seed.py)
`_seed_letters()` read the cover letter markdown file but never stored it. `body_path` was empty.
**Fix**: Use `LetterService.convert_to_html()` + `store_body()` after inserting the DB record.

### Bug 2: Letter export-md returned JSON not markdown (letters.py route)
`/api/v1/letters/export-md/{uuid}` returned `{"markdown": md, "filename": ..., "uuid": ...}`. Frontend's `exportMarkdown()` wrote the raw JSON to `.md` file.
**Fix**: Return `PlainTextResponse(md, media_type="text/markdown")` with Content-Disposition, matching the already-correct todo export-md.

### Bug 3: Journal export-md same JSON-wrapping issue (journal.py route)
`/api/v1/journal/export-md/{uuid}` returned `{"type": "markdown", "data": md}`.
**Fix**: Same PlainTextResponse fix.

### Bug 4: Ctrl+P letter print used window.print() instead of render URL
Commit `d1cd2ad` fixed the Print toolbar button to use the render endpoint but forgot to update the Ctrl+P handler.
**Fix**: Ctrl+P handler (`handleKeydown`) now calls `printLetter()` for consistent behavior.

### Bug 5: !todo list (investigated - verified working)
`!todo list` backend returns `{"type": "todo-list", ...}` and the frontend correctly renders `TodoListTab`. E2E test passes.

## Test Results
- 203/203 backend tests pass
- 28/28 comprehensive Playwright E2E tests pass
- 11/11 basic Playwright E2E tests pass

## Systematic Review
Checked all export-md endpoints:
- `todo`: Already correct (PlainTextResponse) ✓
- `journal`: Now fixed ✓
- `letters`: Now fixed ✓
- Calendar ICS and contacts VCF use JSON wrapping but are handled differently (ExportDialog component parses JSON)
