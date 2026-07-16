# Email & Letter Send Form Enhancements (2026-07-01)

## Changes Made
Branch: `feat/email-letter-send-enhancements`

### ComposeEmail.svelte
- Contact-based email suggestions for To/CC/BCC via `<datalist>` 
- LLM Ask button opens panel even with empty fields (via `openPanel()`)
- `q` key while dirty prompts "Save as draft?" before closing tab

### LetterForm.svelte
- Ctrl+S draft save with Save Draft button + draft UUID tracking
- LLM co-writing integration (Ask LLM button + CowritePanel)
- Inline contact suggestion popup for recipient field (partial text match, shows up to 8)
- `q` key while dirty prompts "Save as draft?" before closing tab

### CowriteEngine.svelte.js
- Added `openPanel()` method — opens the cowrite panel without requiring an instruction
- `startCowrite()` now always sets `isActive=true` so panel shows even if empty instruction

### Backend
- `core/drafts.py`: Added `"letter"` to `_VALID_DOMAINS`
- `routes/drafts.py`: Added `"letter"` to `DraftSaveRequest` domain regex pattern
- `handlers/drafts.py`: Added `@command("letter.draft")` with list/recall support
- `tree.py`: Added `draft` sub-commands under email, journal, todo, calendar, letter

### Frontend Integration
- `StatusPopup.svelte`: Added `"letter"` → `"letter-send"` in draft recall mapping
- `HomeTab.svelte`: Added `letter list/search` to `detectPersistentType`
- `App.svelte`: Already had `letter list` in `detectPersistentType`
