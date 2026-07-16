# !letter send — Rich GUI Form Feature

Issue: https://github.com/Ron-RONZZ-org/lighterbird/issues/66

## Proposal Summary
Implement a richer GUI form for `!letter send` with:
1. Inline multiline body editor with format dropdown (markdown/html/text) + file upload toggle
2. Letterhead: sender top-left, recipient right-aligned below (deviates from current AGENTS-letter.md which had sender top-right)
3. Multiline sender/recipient fields with import from `!user info` / `!contact` via search dialog

## Architect Assessment
- Approved — no major architectural restructuring needed
- Backend changes are minimal: new profiles REST API + one small fix to POST /letters
- Frontend changes: moderate (1 rewrite + 2 new components)
- Risk: file size limits → split into sub-components

## Key Decisions
- Letterhead layout: proposal overrides current AGENTS-letter.md convention (user is product owner)
- Body conversion stays server-side (single source of truth in `convert_to_html()`)
- Search dialog should be generic/reusable
- Need profiles REST API (currently CLI-only)

## Implementation Order
1. Backend: profiles REST API routes
2. Backend: fix POST /letters body_format handling
3. Backend: update letterhead CSS in _generate_letter_html()
4. Document: update AGENTS-letter.md layout rule
5. Frontend: SearchDialog.svelte
6. Frontend: LetterBodyEditor.svelte
7. Frontend: rewrite LetterForm.svelte
