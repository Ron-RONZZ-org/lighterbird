# AGENTS-profiles.md — Profiles Module Agent Instructions

## Summary

User identity profiles module for lighterbird. Provides CRUD for named profiles that store personal information, contact details, and custom fields — used for letter sender resolution, email identity selection, and personalization.

## Purpose and Expected Behavior

`src/lighterbird/profiles/` provides:

- **`db.py`** — `user_profiles` table schema with JSON fields for structured data
- **`services/profiles.py`** — `ProfileService(CRUDService)`: create, read, update, delete, search profiles

## Constraints and Invariants

- **Profiles are named identities** — e.g., "work", "home", "personal". Each has a unique name.
- **JSON columns for custom fields** — arbitrary key-value pairs stored as JSON for flexibility
- **Sender resolution in letter module** — `sender_profile` column in letters references `user_profiles.uuid`
- **No authentication linkage** — profiles are not user accounts; they are identity descriptors for a single-user app
- **Required fields: name, given_name, family_name** — all other fields are optional
- **Optional fields include:** organization, email, phone, address (street, city, postal_code, country), photo, birthday, notes, custom_fields

## Input/Output Expectations

- `!user info list` returns `{"type": "status", ...}` with profile list
- `!user info add` opens a form (interactive) — rendered by `DynamicForm`
- `!user info <uuid>` returns a single profile
- Each profile can be referenced by letter send, email compose, and print layouts

## Documentation Reference

- Letter module (`letter/`) — primary consumer of profiles for sender resolution
- Email module (`email/`) — secondary consumer for email identity selection
- Core (`core/`) — CRUDService base class

## Domain-Specific Rules for Agents

1. **Lightweight schema.** Profiles have only ~15 columns — no complex relationships, no junction tables.
2. **JSON custom_fields for extensibility.** Rather than adding new columns for every possible field, use the `custom_fields` JSON column. Validate with `_validate_json_field()`.
3. **Single-user assumption.** There is no multi-user authentication. Profiles represent different hats the same person wears (work vs personal), not different people.
4. **CRUDService base.** Follows the same `CRUDService` pattern as contacts, journal, and todo modules.
5. **First-class reference target.** Profiles are referenced by UUID from letters, email drafts, and potentially calendar events. Maintain referential integrity at the application layer.
