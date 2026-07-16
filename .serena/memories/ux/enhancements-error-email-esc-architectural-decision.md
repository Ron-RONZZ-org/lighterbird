# Enhancements: Error handling, !email send, ESC, !email list — Architectural Decision (2026-06-28)

## Issue
https://github.com/Ron-RONZZ-org/lighterbird/issues/53

## Decisions per @architect review

| Item | Verdict | Rationale |
|------|---------|-----------|
| 1. Error messages | ✅ Approved | ~8 lines fix in commandExecutor.js, content-type check before resp.json() |
| 2. !email send | ✅ Approved | Backend already supports bcc/attachments/html_body in SMTPClient; add fields to SendRequest + ComposeEmail UI |
| 3. ESC behavior | ✅ Approved | document.activeElement?.blur() in TabView handleKeydown; ~15 lines |
| 4a. f→/ shortcut | ✅ Approved (universal) | Must change ALL list tabs or none — inconsistency worse than different keys |
| 4b.1 Folder tree + 4c Sort/group | ✅ Approved as separate work | EmailFolderTree.svelte (~300 lines) + toolbar mods; pure frontend grouping |
| 4b.2 Drag-drop folder move | ⚠️ Track separately | Complex IMAP semantics, needs new PATCH endpoint |
| 4d. Config persistence | ❌ Deferred | Paradigm conflict with !command flags; undefined scope |

## Implementation Order

Sprint 1 (parallel): Items 1, 3, 4a
Sprint 2 (parallel): Item 2 (backend + frontend)
Sprint 3: Item 4b.1+4c
