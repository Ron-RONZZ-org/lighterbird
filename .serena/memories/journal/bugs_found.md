# Bugs Found in Journal Module During Test Writing

## 1. `date` column has `NOT NULL` with no default — breaks any create without explicit date

**File:** `src/lighterbird/journal/db.py` line 19
**Schema:**
```sql
date TEXT NOT NULL,
```
The `date` column is NOT NULL but has no DEFAULT value. The CRUDService's `create()` method only sets `uuid`, `created_at`, and `updated_at` — not `date`. Any call to `svc.create()` that doesn't include `"date"` in the input data raises `sqlite3.IntegrityError: NOT NULL constraint failed: journal.date`.

**Impact:** All journal creation code paths (CLI, API) that don't explicitly pass a date will crash.

**Fix:** Either:
- Add a default value to the schema: `date TEXT NOT NULL DEFAULT (date('now'))`
- Or override `_post_create` in `JournalService` to set `date` when missing

## 2. `import_md` re-uses original UUID — UNIQUE constraint conflict on re-import

**File:** `src/lighterbird/journal/services/journal.py` line 71-82
When importing from markdown, the `uuid` from the frontmatter is passed directly to `create()`. The CRUDService's `create()` does `data.setdefault(self._pk_column, ...)` — it only generates a new UUID if none is provided. So if an exported file is re-imported without deleting the original, it hits `UNIQUE constraint failed: journal.uuid`.

**Impact:** Round-trip export/import fails unless the original entry is deleted first.

**Potential fix:** Strip the UUID from the imported data (or use a different import key) to always generate a fresh UUID on import.
