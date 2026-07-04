# AGENTS-contacts.md — Contacts Module Agent Instructions

## Summary

Contact management module for lighterbird. Provides CRUD for contacts, FTS5 search, VCF import/export, category tagging, and deduplication.

## Purpose and Expected Behavior

`src/lighterbird/contacts/` provides:

- **`db.py`** — `contacts` table schema with FTS5 virtual table, category join table
- **`services/contacts.py`** — `ContactService(CRUDService)`: create, read, update, delete, search, dedup, VCF I/O

## Constraints and Invariants

- **FTS5 index on name, email, organization, notes** — used for search and autocomplete
- **Emails stored as JSON array** — `[{"value": "a@b.com", "tag": "work"}, ...]` in a single column
- **Phones stored as JSON array** — same pattern as emails
- **Dedup uses email address matching** — case-insensitive, normalized
- **VCF import supports v3.0 and v4.0** — standard vCard format
- **Categories use a junction table** — `contact_categories` for many-to-many assignment

## Input/Output Expectations

- `!contact list` returns `{"type": "contacts-list", ...}` — rendered by `ContactsListTab`
- `!contact add` returns `{"type": "status", ...}` with the new contact UUID
- `!contact export vcf <uuid>` returns a VCF download
- `!contact import vcf <path>` returns import count
- `search(query, limit)` searches via FTS5 MATCH, returns `list[dict]`
- `dedup()` groups contacts by normalized email, returns candidate pairs

## Documentation Reference

- Email module (`email/`) — sibling module, shares the account/contacts relationship pattern
- [A-lien AGENTS.md](../../A-lien/AGENTS.md) — original source for contact management

## Domain-Specific Rules for Agents

1. **Simplified from A-lien.** A-lien's `KontaktoService` was tightly coupled with the email module. The lighterbird `ContactService` is fully standalone, referencing email accounts only by `account_uuid`.
2. **JSON columns for structured data.** Emails and phones use JSON columns. Validate with `_validate_email_json()` / `_validate_phone_json()` in the service layer before write.
3. **VCF is the primary exchange format.** Interop with external address books requires correct vCard v3.0/v4.0 support.
4. **Keep FTS5 current.** The FTS5 index must be updated on every create/update/delete of contacts. This is handled by triggers in `db.py`.
5. **No Esperanto in column names.** All columns use English names (e.g., `given_name`, `family_name`, `organization`).
