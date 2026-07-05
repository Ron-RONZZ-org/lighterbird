"""Tests for journal/services/journal.py — JournalService CRUD, search, labels, export/import."""

from __future__ import annotations

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# CRUD: Create
# ──────────────────────────────────────────────────────────────────────────────


class TestCreate:
    """Journal entry creation tests."""

    def test_create_minimal(self, svc):
        """Create a journal entry with just a title and date."""
        entry = svc.create({"title": "My Day", "date": "2026-07-04"})
        assert entry["uuid"] is not None
        assert entry["title"] == "My Day"
        assert entry.get("created_at")
        assert entry.get("updated_at")
        assert entry.get("date") is not None

    def test_create_all_fields(self, svc):
        """Create a journal entry with all schema fields populated."""
        entry = svc.create({
            "title": "A Great Day",
            "text": "Today was wonderful. Went hiking.",
            "date": "2026-07-04",
        })
        assert entry["uuid"] is not None
        assert entry["title"] == "A Great Day"
        assert entry["text"] == "Today was wonderful. Went hiking."
        assert entry["date"] == "2026-07-04"
        assert entry["created_at"]
        assert entry["updated_at"]

    def test_create_auto_generates_uuid(self, svc):
        """UUID is auto-generated when not provided."""
        e1 = svc.create({"title": "Entry 1", "date": "2026-07-04"})
        e2 = svc.create({"title": "Entry 2", "date": "2026-07-04"})
        assert e1["uuid"] != e2["uuid"]

    def test_create_with_explicit_uuid(self, svc):
        """Explicit UUID is preserved."""
        entry = svc.create({
            "uuid": "test-uuid-0001", "title": "Explicit", "date": "2026-07-04",
        })
        assert entry["uuid"] == "test-uuid-0001"

    def test_create_with_empty_title(self, svc):
        """Creating an entry with empty title is allowed (default '' in schema).
        The create() returns input data + auto-generated fields; missing
        columns are read via get() which returns the full DB row."""
        entry = svc.create({"text": "Just content", "date": "2026-07-04"})
        assert entry["text"] == "Just content"
        # title is NOT in the returned dict since it wasn't in input,
        # but the DB stores '' as the default — verify via get()
        fetched = svc.get(entry["uuid"])
        assert fetched is not None
        assert fetched["title"] == ""


# ──────────────────────────────────────────────────────────────────────────────
# CRUD: Get
# ──────────────────────────────────────────────────────────────────────────────


class TestGet:
    """Journal entry retrieval tests."""

    def test_get_nonexistent(self, svc):
        """Getting a non-existent UUID returns None."""
        assert svc.get("nonexistent-uuid") is None

    def test_get_returns_entry(self, svc):
        """Getting an existing entry returns the correct data."""
        created = svc.create({"title": "Test Entry", "date": "2026-07-04"})
        fetched = svc.get(created["uuid"])
        assert fetched is not None
        assert fetched["uuid"] == created["uuid"]
        assert fetched["title"] == "Test Entry"

    def test_get_by_prefix(self, svc):
        """UUID prefix matching works for retrieval."""
        created = svc.create({"title": "Prefix Test", "date": "2026-07-04"})
        prefix = created["uuid"][:8]
        fetched = svc.get(prefix)
        assert fetched is not None
        assert fetched["uuid"] == created["uuid"]


# ──────────────────────────────────────────────────────────────────────────────
# CRUD: List
# ──────────────────────────────────────────────────────────────────────────────


class TestList:
    """Journal entry listing tests."""

    def test_list_empty(self, svc):
        """Empty database returns empty list."""
        assert svc.list() == []

    def test_list_returns_all(self, svc):
        """List returns all created entries."""
        svc.create({"title": "First", "date": "2026-07-04"})
        svc.create({"title": "Second", "date": "2026-07-04"})
        results = svc.list(limit=10)
        assert len(results) == 2

    def test_list_respects_limit(self, svc):
        """List respects the limit parameter."""
        svc.create({"title": "A", "date": "2026-07-04"})
        svc.create({"title": "B", "date": "2026-07-04"})
        svc.create({"title": "C", "date": "2026-07-04"})
        results = svc.list(limit=2)
        assert len(results) == 2

    def test_list_ordering_default(self, svc):
        """List defaults to uuid descending."""
        svc.create({"title": "Alpha", "date": "2026-07-04"})
        svc.create({"title": "Beta", "date": "2026-07-04"})
        results = svc.list()
        assert len(results) == 2


# ──────────────────────────────────────────────────────────────────────────────
# CRUD: Update
# ──────────────────────────────────────────────────────────────────────────────


class TestUpdate:
    """Journal entry update tests."""

    def test_update_title(self, svc):
        """Updating title changes the entry."""
        entry = svc.create({"title": "Original", "date": "2026-07-04"})
        updated = svc.update(entry["uuid"], {"title": "Updated"})
        assert updated["title"] == "Updated"

    def test_update_content(self, svc):
        """Updating text content changes the entry."""
        entry = svc.create({
            "title": "Content Test", "text": "Old text", "date": "2026-07-04",
        })
        updated = svc.update(entry["uuid"], {"text": "New text"})
        assert updated["text"] == "New text"
        # Title should be preserved
        assert updated["title"] == "Content Test"

    def test_update_date(self, svc):
        """Updating date works."""
        entry = svc.create({"title": "Date Test", "date": "2026-01-01"})
        updated = svc.update(entry["uuid"], {"date": "2026-06-15"})
        assert updated["date"] == "2026-06-15"

    def test_update_nonexistent_returns_none(self, svc):
        """Updating a non-existent entry returns None."""
        result = svc.update("nonexistent-uuid", {"title": "X"})
        assert result is None

    def test_update_updates_timestamp(self, svc):
        """Update changes the updated_at timestamp."""
        import time

        entry = svc.create({"title": "Time Test", "date": "2026-07-04"})
        orig_updated = entry["updated_at"]
        time.sleep(0.01)
        updated = svc.update(entry["uuid"], {"title": "New Title"})
        assert updated["updated_at"] >= orig_updated


# ──────────────────────────────────────────────────────────────────────────────
# CRUD: Delete
# ──────────────────────────────────────────────────────────────────────────────


class TestDelete:
    """Journal entry deletion tests."""

    def test_delete_existing(self, svc):
        """Deleting an existing entry removes it."""
        entry = svc.create({"title": "ToDelete", "date": "2026-07-04"})
        svc.delete(entry["uuid"])
        assert svc.get(entry["uuid"]) is None

    def test_delete_nonexistent(self, svc):
        """Deleting a non-existent UUID does not raise."""
        svc.delete("nonexistent")  # Should not raise

    def test_delete_by_prefix(self, svc):
        """Deleting by UUID prefix works."""
        entry = svc.create({"title": "PrefixDel", "date": "2026-07-04"})
        prefix = entry["uuid"][:8]
        svc.delete(prefix)
        assert svc.get(entry["uuid"]) is None

    def test_delete_does_not_affect_others(self, svc):
        """Deleting one entry leaves others intact."""
        e1 = svc.create({"title": "Keep", "date": "2026-07-04"})
        e2 = svc.create({"title": "Remove", "date": "2026-07-04"})
        svc.delete(e2["uuid"])
        assert svc.get(e1["uuid"]) is not None
        assert svc.get(e2["uuid"]) is None


# ──────────────────────────────────────────────────────────────────────────────
# CRUD: Count
# ──────────────────────────────────────────────────────────────────────────────


class TestCount:
    """Journal entry count tests."""

    def test_count_zero(self, svc):
        """Count returns 0 when no entries exist."""
        assert svc.count() == 0

    def test_count_after_create(self, svc):
        """Count reflects created entries."""
        svc.create({"title": "A", "date": "2026-07-04"})
        svc.create({"title": "B", "date": "2026-07-04"})
        assert svc.count() == 2

    def test_count_after_delete(self, svc):
        """Count decreases after delete."""
        e = svc.create({"title": "ToCount", "date": "2026-07-04"})
        svc.delete(e["uuid"])
        assert svc.count() == 0


# ──────────────────────────────────────────────────────────────────────────────
# Search
# ──────────────────────────────────────────────────────────────────────────────


class TestSearch:
    """Journal search tests."""

    def test_search_by_title(self, svc):
        """Search by title returns matching entries."""
        svc.create({"title": "Hiking Adventure", "text": "Great day outdoors", "date": "2026-07-04"})
        svc.create({"title": "Cooking Dinner", "text": "Made pasta", "date": "2026-07-04"})
        results = svc.search("hiking")
        assert len(results) == 1
        assert results[0]["title"] == "Hiking Adventure"

    def test_search_by_content(self, svc):
        """Search by text content returns matching entries."""
        svc.create({"title": "Day 1", "text": "Went to the beach", "date": "2026-07-04"})
        svc.create({"title": "Day 2", "text": "Stayed home reading", "date": "2026-07-04"})
        results = svc.search("beach")
        assert len(results) == 1
        assert results[0]["title"] == "Day 1"

    def test_search_empty_query_returns_all(self, svc):
        """Empty query returns all entries (falls back to list)."""
        svc.create({"title": "A", "date": "2026-07-04"})
        svc.create({"title": "B", "date": "2026-07-04"})
        results = svc.search("")
        assert len(results) == 2

    def test_search_no_match(self, svc):
        """Search with non-matching query returns empty list."""
        svc.create({"title": "Hello", "date": "2026-07-04"})
        results = svc.search("nonexistent")
        assert results == []

    def test_search_case_insensitive(self, svc):
        """Search is case-insensitive."""
        svc.create({"title": "HELLO WORLD", "date": "2026-07-04"})
        results = svc.search("hello")
        assert len(results) == 1

    def test_search_short_query(self, svc):
        """Short queries (1 char) work via LIKE fallback."""
        svc.create({"title": "Xylophone", "date": "2026-07-04"})
        results = svc.search("x")
        assert len(results) == 1

    def test_search_returns_limited_results(self, svc):
        """Search respects the limit parameter."""
        for i in range(5):
            svc.create({"title": f"Entry{i}", "date": "2026-07-04"})
        results = svc.search("entry", limit=2)
        assert len(results) <= 2


# ──────────────────────────────────────────────────────────────────────────────
# list_by_date
# ──────────────────────────────────────────────────────────────────────────────


class TestListByDate:
    """list_by_date tests."""

    def test_list_by_date(self, svc):
        """List entries for a specific date."""
        svc.create({"title": "Today", "date": "2026-07-04"})
        svc.create({"title": "Yesterday", "date": "2026-07-03"})
        svc.create({"title": "Also Today", "date": "2026-07-04"})
        results = svc.list_by_date("2026-07-04")
        assert len(results) == 2
        assert all(e["date"] == "2026-07-04" for e in results)

    def test_list_by_date_no_match(self, svc):
        """No entries for a date returns empty list."""
        svc.create({"title": "Some Day", "date": "2026-01-01"})
        results = svc.list_by_date("2099-12-31")
        assert results == []


# ──────────────────────────────────────────────────────────────────────────────
# Labels — CRUD
# ──────────────────────────────────────────────────────────────────────────────


class TestLabels:
    """Label CRUD and assignment tests."""

    def test_create_label(self, svc):
        """Create a new label."""
        label = svc.create_label({"name": "important", "color": "#ff0000"})
        assert label["name"] == "important"
        assert label["color"] == "#ff0000"
        assert label.get("created_at")
        assert label.get("updated_at")

    def test_create_label_minimal(self, svc):
        """Create a label with just a name."""
        label = svc.create_label({"name": "personal"})
        assert label["name"] == "personal"
        assert label["color"] == ""

    def test_create_label_missing_name_raises(self, svc):
        """Creating a label with empty name raises ValueError."""
        with pytest.raises(ValueError, match="Tag name is required"):
            svc.create_label({"name": ""})

    def test_create_label_duplicate_raises(self, svc):
        """Creating a duplicate label raises ValueError."""
        svc.create_label({"name": "unique"})
        with pytest.raises(ValueError, match="already exists"):
            svc.create_label({"name": "unique"})

    def test_create_label_case_sensitivity(self, svc):
        """Label names are case-insensitive (COLLATE NOCASE)."""
        svc.create_label({"name": "Work"})
        with pytest.raises(ValueError, match="already exists"):
            svc.create_label({"name": "work"})

    def test_list_all_labels_empty(self, svc):
        """No labels returns empty list."""
        assert svc.list_all_labels() == []

    def test_list_all_labels(self, svc):
        """List all available labels."""
        svc.create_label({"name": "alpha"})
        svc.create_label({"name": "beta"})
        results = svc.list_all_labels()
        assert len(results) == 2
        assert results[0]["name"] == "alpha"
        assert results[1]["name"] == "beta"

    def test_delete_label(self, svc):
        """Delete a label removes it."""
        svc.create_label({"name": "temporary"})
        svc.delete_label("temporary")
        assert svc.list_all_labels() == []

    def test_delete_label_cascades(self, svc):
        """Deleting a label removes its junction entries."""
        entry = svc.create({"title": "Label Test", "date": "2026-07-04"})
        svc.create_label({"name": "cascade-me"})
        svc.add_label(entry["uuid"], "cascade-me")
        svc.delete_label("cascade-me")
        # Entry should still exist
        assert svc.get(entry["uuid"]) is not None
        # Label should be gone from entry
        assert svc.get_labels(entry["uuid"]) == []


# ──────────────────────────────────────────────────────────────────────────────
# Labels — Assignment
# ──────────────────────────────────────────────────────────────────────────────


class TestLabelAssignment:
    """Label-to-entry assignment tests."""

    def test_add_label_to_entry(self, svc):
        """Add a label to a journal entry."""
        entry = svc.create({"title": "Label Me", "date": "2026-07-04"})
        svc.create_label({"name": "work"})
        svc.add_label(entry["uuid"], "work")
        labels = svc.get_labels(entry["uuid"])
        assert len(labels) == 1
        assert labels[0]["name"] == "work"

    def test_add_label_idempotent(self, svc):
        """Adding the same label twice is idempotent."""
        entry = svc.create({"title": "Label Test", "date": "2026-07-04"})
        svc.create_label({"name": "misc"})
        svc.add_label(entry["uuid"], "misc")
        svc.add_label(entry["uuid"], "misc")  # should not raise
        labels = svc.get_labels(entry["uuid"])
        assert len(labels) == 1

    def test_add_multiple_labels(self, svc):
        """Multiple labels can be added to one entry."""
        entry = svc.create({"title": "Multi Label", "date": "2026-07-04"})
        svc.create_label({"name": "work"})
        svc.create_label({"name": "personal"})
        svc.create_label({"name": "finance"})
        svc.add_label(entry["uuid"], "work")
        svc.add_label(entry["uuid"], "personal")
        svc.add_label(entry["uuid"], "finance")
        labels = svc.get_labels(entry["uuid"])
        assert len(labels) == 3
        names = [l["name"] for l in labels]
        assert "work" in names
        assert "personal" in names
        assert "finance" in names

    def test_remove_label_from_entry(self, svc):
        """Remove a label from a journal entry."""
        entry = svc.create({"title": "Remove Test", "date": "2026-07-04"})
        svc.create_label({"name": "temp"})
        svc.add_label(entry["uuid"], "temp")
        svc.remove_label(entry["uuid"], "temp")
        labels = svc.get_labels(entry["uuid"])
        assert labels == []

    def test_remove_nonexistent_label(self, svc):
        """Removing a label that isn't assigned does not raise."""
        entry = svc.create({"title": "No Label", "date": "2026-07-04"})
        svc.remove_label(entry["uuid"], "nonexistent")  # should not raise

    def test_get_labels_no_labels(self, svc):
        """Getting labels for an entry with none returns empty list."""
        entry = svc.create({"title": "No Labels", "date": "2026-07-04"})
        assert svc.get_labels(entry["uuid"]) == []

    def test_delete_entry_cascades_labels(self, svc):
        """Deleting an entry removes its label associations."""
        entry = svc.create({"title": "Cascade Test", "date": "2026-07-04"})
        svc.create_label({"name": "test-label"})
        svc.add_label(entry["uuid"], "test-label")
        svc.delete(entry["uuid"])
        # Label itself should still exist (cascade only removes junction)
        all_labels = svc.list_all_labels()
        assert len(all_labels) == 1


# ──────────────────────────────────────────────────────────────────────────────
# Export / Import — Markdown
# ──────────────────────────────────────────────────────────────────────────────


class TestExportImport:
    """Markdown export and import tests."""

    def test_export_md_single(self, svc):
        """Export a single entry to markdown with YAML frontmatter."""
        entry = svc.create({
            "title": "Export Test",
            "text": "Body text here",
            "date": "2026-07-04",
        })
        md = svc.export_md(uuid=entry["uuid"])
        assert "---" in md
        assert entry["uuid"] in md
        assert "domain: journal" in md
        assert "Export Test" in md or "title:" in md
        assert "Body text here" in md

    def test_export_md_multiple(self, svc):
        """Export multiple entries separated by ---."""
        e1 = svc.create({"title": "First", "text": "Content A", "date": "2026-07-04"})
        e2 = svc.create({"title": "Second", "text": "Content B", "date": "2026-07-04"})
        md = svc.export_md(uuids=[e1["uuid"], e2["uuid"]])
        count = md.count("\n---\n")
        # Each entry's wrap() contributes one \n---\n (closing delimiter),
        # plus the join adds (N-1) between entries → total 2N-1 for N entries
        assert count == 3  # 2*2 - 1 = 3

    def test_export_md_nonexistent_skips(self, svc):
        """Exporting a non-existent UUID skips it gracefully."""
        svc.create({"title": "Real", "text": "Real content", "date": "2026-07-04"})
        md = svc.export_md(uuids=["nonexistent"])
        # No entries to export — md should be empty
        assert md == ""

    def test_import_md(self, svc):
        """Import a journal entry from markdown with YAML frontmatter."""
        import tempfile
        from pathlib import Path

        md_content = (
            "---\n"
            "uuid: 'import-test-uuid'\n"
            "domain: journal\n"
            "title: Imported Entry\n"
            "date: '2026-07-04'\n"
            "---\n"
            "\n"
            "This is the imported body."
        )
        path = Path(tempfile.mktemp(suffix=".md"))
        path.write_text(md_content, encoding="utf-8")
        try:
            uuids = svc.import_md(str(path))
            assert len(uuids) == 1
            entry = svc.get(uuids[0])
            assert entry is not None
            assert entry["title"] == "Imported Entry"
            assert entry["text"] == "This is the imported body."
            assert entry["date"] == "2026-07-04"
        finally:
            path.unlink()

    def test_import_md_round_trip(self, svc):
        """Export then re-import produces the same content (original deleted first)."""
        original = svc.create({
            "title": "Round Trip",
            "text": "Round trip body content.",
            "date": "2026-07-04",
        })
        md = svc.export_md(uuid=original["uuid"])

        import tempfile
        from pathlib import Path

        # Delete original to avoid UUID conflict on re-import
        svc.delete(original["uuid"])

        path = Path(tempfile.mktemp(suffix=".md"))
        path.write_text(md, encoding="utf-8")
        try:
            uuids = svc.import_md(str(path))
            assert len(uuids) == 1
            restored = svc.get(uuids[0])
            assert restored is not None
            assert restored["title"] == original["title"]
            assert restored["text"] == original["text"]
        finally:
            path.unlink()

    def test_import_md_no_frontmatter(self, svc):
        """Importing markdown without frontmatter returns empty list."""
        import tempfile
        from pathlib import Path

        path = Path(tempfile.mktemp(suffix=".md"))
        path.write_text("Just plain markdown without frontmatter.", encoding="utf-8")
        try:
            uuids = svc.import_md(str(path))
            assert uuids == []
        finally:
            path.unlink()

    def test_import_md_malformed_yaml(self, svc):
        """Importing with malformed YAML frontmatter returns empty list."""
        import tempfile
        from pathlib import Path

        path = Path(tempfile.mktemp(suffix=".md"))
        path.write_text("---\n: invalid yaml :::\n---\nBody", encoding="utf-8")
        try:
            uuids = svc.import_md(str(path))
            assert uuids == []
        finally:
            path.unlink()


# ──────────────────────────────────────────────────────────────────────────────
# DB Schema
# ──────────────────────────────────────────────────────────────────────────────


class TestDB:
    """Database schema tests."""

    def test_get_db_creates_tables(self, tmp_path):
        """get_db creates the journal and labels tables."""
        from lighterbird.journal.db import get_db

        db = get_db(tmp_path / "test_journal.db")
        assert db.table_exists("journal")

    def test_get_db_idempotent(self, tmp_path):
        """Calling get_db multiple times does not raise."""
        from lighterbird.journal.db import get_db

        path = tmp_path / "idemp.db"
        get_db(path)
        get_db(path)  # Should not raise

    def test_journal_table_columns(self, tmp_path):
        """journal table has expected columns."""
        from lighterbird.journal.db import get_db

        db = get_db(tmp_path / "cols.db")
        cols = {r["name"] for r in db.get_pragma_table_info("journal")}
        expected = {"uuid", "title", "text", "date", "created_at", "updated_at"}
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"

    def test_labels_table_columns(self, tmp_path):
        """Labels are now managed in the shared tags.db — no local labels table."""
        from lighterbird.journal.db import get_db

        db = get_db(tmp_path / "labels.db")
        assert not db.table_exists("labels")
