# GUI Account Management — Approved Plan

Decision: Implement GUI management buttons for LLM profiles, email accounts, and calendar accounts.

## Key Architectural Decisions (per @architect review)

1. **REST for LLM profiles** — Add to new `routes/llm.py` (extract from `routes/chat.py`)
2. **AccountList.svelte** as shared component — do NOT extend StatusPopup.svelte
3. **Blocking popup forms** consistent with LlmSetupModal.svelte
4. **Add PATCH for LLM profiles** — new `LLMProviderWrapper.modify_profile()` method
5. **Add PATCH and DELETE for calendar** — verify backend cleanup
6. **StatusPopup.svelte unchanged** — backward compat

## REST endpoints to add

- GET/POST/PATCH/DELETE /api/v1/llm/profiles[/{name}][/load]
- PATCH /api/v1/email/accounts/{uuid}
- PATCH/DELETE /api/v1/calendar/calendars/{uuid}

## Frontend components

- AccountList.svelte (reusable), LlmProfileForm.svelte, EmailAccountForm.svelte, CalendarAccountForm.svelte

## Implementation Order

1. Backend REST endpoints + modify_profile()
2. Frontend api.js wrappers
3. AccountList.svelte
4. Form components
5. Wire overlays
6. Empty-state polish

Issue: https://github.com/Ron-RONZZ-org/lighterbird/issues/8
