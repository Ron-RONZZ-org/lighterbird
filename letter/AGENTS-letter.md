# AGENTS-letter.md — Letter Module Agent Instructions

## Summary

Paper letter management module for lighterbird. Provides CRUD for letters (sent and received), body rendering as HTML for print/PDF, conversation threading via `respond_to_uuid`, and sender/recipient resolution from user profiles and contacts.

## Purpose and Expected Behavior

`src/lighterbird/letter/` provides:

- **`db.py`** — `letters` table with `direction` (sent/received), `respond_to_uuid` self-reference, body paths
- **`services/letters.py`** — `LetterService(CRUDService)`: list with filters, conversation grouping, body conversion (markdown/HTML/text), thread resolution
- **Command handlers** — `!letter list|add|send|view`

## Constraints and Invariants

- **PDF rendering is hybrid**: backend generates HTML+CSS, browser prints to PDF. No server-side PDF library is a hard dependency. Optional `fpdf2` for CLI-only `!letter pdf --output file.pdf` under `lighterbird[pdf]` extra.
- **Letter body storage**: the `body_path` column stores the path to the body content file. HTML is the canonical format — markdown and plain text are converted to HTML on storage.
- **Sender resolution**: `sender_profile` references `!user info` profiles. `sender_manual` is free-text. If both present, `sender_profile` takes precedence for structured data, but the letter UI should show both.
- **Recipient resolution**: `recipient_contact` references `!contact`. `recipient_manual` is free-text. Same precedence rule.
- **Conversation threading**: `respond_to_uuid` is a self-referencing FK. `!letter list --group conversation` uses a recursive CTE to group letters into threads.
- **No FTS5 initially**: the letters table is small enough for LIKE-based search. FTS5 can be added later if needed.

## Input/Output Expectations

- `!letter list` returns `{"type": "letter-list", ...}` — rendered by `LetterListTab`
- `!letter add` and `!letter send` return `{"type": "status", ...}` with the new letter UUID
- `!letter view` returns `{"type": "letter-view", ...}` with HTML body — rendered by `LetterViewTab`
- `GET /api/v1/letters/letters/{uuid}/body` returns the raw HTML body content

## Documentation Reference

- Email module (`email/`) — primary reference pattern for file body handling and send flow
- Contacts module (`contacts/`) — address resolution for recipient
- Profiles module (`profiles/`) — sender profile resolution

## Domain-Specific Rules for Agents

1. **Letterhead template**: generate letterhead as HTML+CSS programmatically. Sender details at top-right, recipient at top-left, date below, object line, body. Style mimics classic letter layout (serif fonts, appropriate margins).
2. **Body format detection**: on file upload, detect format from extension (.md, .html, .txt, .odt). Convert all non-HTML to HTML. For .odt, try `python-docx` or similar — fall back to text extraction if unavailable.
3. **Conversation grouping**: use SQL recursive CTE to build thread tree. Each group shows the root letter with reply count.
4. **Keep it lightweight**: letter data is mostly metadata + text. No attachments storage beyond the body content file.
