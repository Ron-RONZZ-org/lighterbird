"""Tests for TodoService — CRUD, tree, templates, export/import, labels, dependencies."""

from __future__ import annotations

import json
import uuid as uuid_mod

import pytest


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_uuid() -> str:
    return str(uuid_mod.uuid4())


# ── Create ──────────────────────────────────────────────────────────────────


class TestCreate:
    """Todo creation tests."""

    def test_create_minimal(self, svc):
        """Create a todo with just a title."""
        todo = svc.create({"title": "Buy groceries"})
        assert todo["uuid"] is not None
        assert todo["title"] == "Buy groceries"
        assert todo.get("created_at")
        assert todo.get("updated_at")
        # status default is in DB, not in returned dict; verify via get()
        fetched = svc.get(todo["uuid"])
        assert fetched["status"] == "pending"

    def test_create_with_description(self, svc):
        """Create with a description."""
        todo = svc.create({"title": "Write docs", "description": "Update the README and API docs"})
        assert todo["description"] == "Update the README and API docs"

    def test_create_with_priority_and_due(self, svc):
        """Create with priority and due_date."""
        todo = svc.create({"title": "Pay bills", "priority": "1", "due_date": "2026-07-15"})
        assert todo["priority"] == "1"
        assert todo["due_date"] == "2026-07-15"

    def test_create_with_dependencies(self, svc):
        """Create a todo that depends on another."""
        parent = svc.create({"title": "Parent task"})
        todo = svc.create({
            "title": "Child task",
            "_depends_on": [parent["uuid"]],
        })
        deps = svc.get_dependencies(todo["uuid"])
        assert len(deps) == 1
        assert deps[0]["uuid"] == parent["uuid"]

    def test_create_with_single_dependency_string(self, svc):
        """Create with _depends_on as a single string (not list)."""
        parent = svc.create({"title": "Blocking task"})
        # Use a string instead of list
        data = {"title": "Blocked", "_depends_on": parent["uuid"]}
        todo = svc.create(data)
        deps = svc.get_dependencies(todo["uuid"])
        assert len(deps) == 1
        assert deps[0]["uuid"] == parent["uuid"]

    def test_create_with_tags(self, svc):
        """Create a todo with tags."""
        todo = svc.create({
            "title": "Tagged task",
            "_tags": ["work", "urgent"],
        })
        # Tags should be attached via add_label
        labels = svc.get_labels(todo["uuid"])
        label_names = [l["name"] for l in labels]
        assert "work" in label_names
        assert "urgent" in label_names

    def test_create_auto_generates_uuid(self, svc):
        """UUID is generated when not provided."""
        todo = svc.create({"title": "Auto UUID"})
        assert todo["uuid"] is not None
        assert len(todo["uuid"]) == 36  # standard UUID format

    def test_create_updates_timestamps(self, svc):
        """Timestamps are set on creation."""
        todo = svc.create({"title": "Timed task"})
        assert todo["created_at"] is not None
        assert todo["updated_at"] is not None
        assert todo["updated_at"] >= todo["created_at"]  # same or later


# ── Get ─────────────────────────────────────────────────────────────────────


class TestGet:
    """Todo retrieval tests."""

    def test_get_existing(self, svc):
        """Get an existing todo by UUID."""
        created = svc.create({"title": "Find me"})
        fetched = svc.get(created["uuid"])
        assert fetched is not None
        assert fetched["uuid"] == created["uuid"]
        assert fetched["title"] == "Find me"

    def test_get_nonexistent(self, svc):
        """Get a non-existent UUID returns None."""
        assert svc.get("nonexistent-uuid") is None

    def test_get_by_prefix(self, svc):
        """UUID prefix matching works."""
        created = svc.create({"title": "Prefix match"})
        prefix = created["uuid"][:8]
        fetched = svc.get(prefix)
        assert fetched is not None
        assert fetched["uuid"] == created["uuid"]

    def test_get_by_short_prefix(self, svc):
        """Short prefix (4 chars) still matches."""
        created = svc.create({"title": "Short prefix"})
        prefix = created["uuid"][:4]
        fetched = svc.get(prefix)
        assert fetched is not None
        assert fetched["uuid"] == created["uuid"]


# ── List ────────────────────────────────────────────────────────────────────


class TestList:
    """Todo listing tests."""

    def test_list_empty(self, svc):
        """Empty database returns empty list."""
        assert svc.list() == []

    def test_list_returns_all(self, svc):
        """List returns all created todos."""
        svc.create({"title": "A"})
        svc.create({"title": "B"})
        results = svc.list(limit=10)
        assert len(results) == 2

    def test_list_respects_limit(self, svc):
        """List respects the limit parameter."""
        for i in range(5):
            svc.create({"title": f"Task {i}"})
        results = svc.list(limit=2)
        assert len(results) == 2

    def test_list_respects_offset(self, svc):
        """List respects the offset parameter."""
        for i in range(5):
            svc.create({"title": f"Task {i}"})
        results = svc.list(limit=10, offset=3)
        assert len(results) == 2  # 5 - 3 = 2

    def test_list_sort_by_created(self, svc):
        """List sorted by created_at DESC (default)."""
        svc.create({"title": "First"})
        svc.create({"title": "Second"})
        results = svc.list(sort="created")
        assert len(results) == 2
        # Second created first in DESC order
        assert results[0]["title"] == "Second"

    def test_list_sort_by_priority(self, svc):
        """List sorted by priority DESC (higher number first)."""
        svc.create({"title": "Low", "priority": "5"})
        svc.create({"title": "High", "priority": "1"})
        results = svc.list(sort="priority")
        assert len(results) == 2
        # CAST(...) DESC means 5 before 1
        assert results[0]["priority"] == "5"
        assert results[1]["priority"] == "1"

    def test_list_sort_by_due(self, svc):
        """List sorted by due_date ASC."""
        svc.create({"title": "Later", "due_date": "2026-12-01"})
        svc.create({"title": "Soon", "due_date": "2026-01-15"})
        svc.create({"title": "No due"})  # NULL last
        results = svc.list(sort="due")
        assert len(results) == 3
        # NULLs should come last
        assert results[0]["title"] == "Soon"
        assert results[1]["title"] == "Later"
        assert results[2]["title"] == "No due"

    def test_list_has_computed_priority(self, svc):
        """List adds _computed_priority to each row."""
        svc.create({"title": "Priority check", "priority": "3"})
        results = svc.list()
        assert len(results) == 1
        assert "_computed_priority" in results[0]

    def test_list_attaches_labels(self, svc):
        """List attaches label info to each todo."""
        todo = svc.create({"title": "Labeled", "_tags": ["test-tag"]})
        results = svc.list()
        assert len(results) == 1
        labels = results[0].get("labels", [])
        assert any(l["name"] == "test-tag" for l in labels)


# ── Update ──────────────────────────────────────────────────────────────────


class TestUpdate:
    """Todo update tests."""

    def test_update_title(self, svc):
        """Update a todo's title."""
        todo = svc.create({"title": "Old title"})
        updated = svc.update(todo["uuid"], {"title": "New title"})
        assert updated is not None
        assert updated["title"] == "New title"

    def test_update_priority(self, svc):
        """Update a todo's priority."""
        todo = svc.create({"title": "Re-prioritize", "priority": "5"})
        updated = svc.update(todo["uuid"], {"priority": "1"})
        assert updated["priority"] == "1"

    def test_update_due_date(self, svc):
        """Update a todo's due date."""
        todo = svc.create({"title": "Set due"})
        updated = svc.update(todo["uuid"], {"due_date": "2026-12-31"})
        assert updated["due_date"] == "2026-12-31"

    def test_update_clear_due_date(self, svc):
        """Clear a previously set due date."""
        todo = svc.create({"title": "Clear due", "due_date": "2026-07-01"})
        updated = svc.update(todo["uuid"], {"due_date": None})
        assert updated["due_date"] is None

    def test_update_nonexistent(self, svc):
        """Update on non-existent UUID returns None."""
        result = svc.update("nonexistent-uuid", {"title": "Nope"})
        assert result is None

    def test_update_updates_timestamp(self, svc):
        """Update changes the updated_at timestamp."""
        import time

        todo = svc.create({"title": "Timestamp check"})
        orig_updated = todo["updated_at"]
        time.sleep(0.01)
        updated = svc.update(todo["uuid"], {"title": "Updated"})
        assert updated["updated_at"] > orig_updated

    def test_update_tags(self, svc):
        """Update replaces tags when _tags is provided."""
        todo = svc.create({"title": "Re-tag", "_tags": ["old-tag"]})
        updated = svc.update(todo["uuid"], {"_tags": ["new-tag"]})
        labels = svc.get_labels(todo["uuid"])
        label_names = [l["name"] for l in labels]
        assert "new-tag" in label_names
        assert "old-tag" not in label_names

    def test_update_preserves_created_at(self, svc):
        """Update does not change created_at."""
        todo = svc.create({"title": "Preserve"})
        orig_created = todo["created_at"]
        svc.update(todo["uuid"], {"title": "Updated"})
        fetched = svc.get(todo["uuid"])
        assert fetched["created_at"] == orig_created


# ── Delete ──────────────────────────────────────────────────────────────────


class TestDelete:
    """Todo deletion tests."""

    def test_delete_existing(self, svc):
        """Delete an existing todo removes it."""
        todo = svc.create({"title": "To delete"})
        svc.delete(todo["uuid"])
        assert svc.get(todo["uuid"]) is None

    def test_delete_nonexistent(self, svc):
        """Delete a non-existent UUID returns False (does not raise)."""
        result = svc.delete("nonexistent")
        assert result is False

    def test_delete_by_prefix(self, svc):
        """Delete by UUID prefix works."""
        todo = svc.create({"title": "Prefix delete"})
        prefix = todo["uuid"][:8]
        svc.delete(prefix)
        assert svc.get(todo["uuid"]) is None

    def test_delete_does_not_affect_others(self, svc):
        """Deleting one todo leaves others intact."""
        t1 = svc.create({"title": "Keep"})
        t2 = svc.create({"title": "Remove"})
        svc.delete(t2["uuid"])
        assert svc.get(t1["uuid"]) is not None
        assert svc.get(t2["uuid"]) is None

    def test_delete_reparents_children(self, svc):
        """Deleting a parent reparents children to grandparent."""
        grandparent = svc.create({"title": "Grandparent"})
        parent = svc.create({"title": "Parent", "parent_uuid": grandparent["uuid"]})
        child = svc.create({"title": "Child", "parent_uuid": parent["uuid"]})
        svc.delete(parent["uuid"])
        # Child should now be reparented to grandparent
        fetched = svc.get(child["uuid"])
        assert fetched["parent_uuid"] == grandparent["uuid"]


# ── Mark done ───────────────────────────────────────────────────────────────


class TestMarkDone:
    """Mark-done tests."""

    def test_mark_done(self, svc):
        """mark_done sets status to 'done'."""
        todo = svc.create({"title": "Finish this"})
        result = svc.mark_done(todo["uuid"])
        assert result is True
        fetched = svc.get(todo["uuid"])
        assert fetched["status"] == "done"

    def test_mark_done_nonexistent(self, svc):
        """mark_done on non-existent UUID returns False."""
        result = svc.mark_done("nonexistent-uuid")
        assert result is False

    def test_mark_done_idempotent(self, svc):
        """mark_done can be called multiple times."""
        todo = svc.create({"title": "Double done"})
        svc.mark_done(todo["uuid"])
        svc.mark_done(todo["uuid"])  # second call should not error
        fetched = svc.get(todo["uuid"])
        assert fetched["status"] == "done"


# ── Tree ────────────────────────────────────────────────────────────────────


class TestTree:
    """Tree/hierarchy tests."""

    def test_get_tree_root_only(self, svc):
        """get_tree returns root-level todos when none have parent."""
        svc.create({"title": "Root 1"})
        svc.create({"title": "Root 2"})
        tree = svc.get_tree()
        assert len(tree) == 2
        for item in tree:
            assert item["children"] == []

    def test_get_tree_parent_child(self, svc):
        """get_tree returns nested structure for parent-child."""
        parent = svc.create({"title": "Parent"})
        child = svc.create({"title": "Child", "parent_uuid": parent["uuid"]})
        tree = svc.get_tree()
        assert len(tree) == 1
        assert tree[0]["title"] == "Parent"
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["title"] == "Child"

    def test_get_tree_max_depth(self, svc):
        """get_tree respects max_depth."""
        parent = svc.create({"title": "L1"})
        child = svc.create({"title": "L2", "parent_uuid": parent["uuid"]})
        grandchild = svc.create({"title": "L3", "parent_uuid": child["uuid"]})
        # max_depth=0: root items included (depth 0), but children excluded
        tree = svc.get_tree(max_depth=0)
        assert len(tree) == 1  # root item L1 at depth 0 is included
        assert tree[0]["title"] == "L1"
        assert tree[0]["children"] == []  # children excluded because depth 1 > max_depth 0

    def test_flatten_tree(self, svc):
        """flatten_tree returns flat list with depth info."""
        parent = svc.create({"title": "Parent"})
        child = svc.create({"title": "Child", "parent_uuid": parent["uuid"]})
        flat = svc.flatten_tree()
        assert len(flat) == 2
        items_by_title = {i["title"]: i for i in flat}
        assert items_by_title["Parent"]["_depth"] == 0
        assert items_by_title["Parent"]["_has_children"] is True
        assert items_by_title["Child"]["_depth"] == 1
        assert items_by_title["Child"]["_has_children"] is False

    def test_get_with_children(self, svc):
        """get_with_children returns a todo with its children."""
        parent = svc.create({"title": "Parent"})
        child = svc.create({"title": "Child", "parent_uuid": parent["uuid"]})
        result = svc.get_with_children(parent["uuid"])
        assert result is not None
        assert result["title"] == "Parent"
        assert len(result["children"]) == 1
        assert result["children"][0]["title"] == "Child"

    def test_get_with_children_nonexistent(self, svc):
        """get_with_children on non-existent UUID returns None."""
        assert svc.get_with_children("nonexistent") is None

    def test_move_as_child(self, svc):
        """move_as_child sets parent_uuid."""
        parent = svc.create({"title": "Parent"})
        child = svc.create({"title": "Child"})
        svc.move_as_child(child["uuid"], parent["uuid"])
        fetched = svc.get(child["uuid"])
        assert fetched["parent_uuid"] == parent["uuid"]

    def test_move_as_child_to_root(self, svc):
        """move_as_child with None clears parent_uuid (moves to root)."""
        parent = svc.create({"title": "Parent"})
        child = svc.create({"title": "Child", "parent_uuid": parent["uuid"]})
        svc.move_as_child(child["uuid"], None)
        fetched = svc.get(child["uuid"])
        assert fetched["parent_uuid"] is None


# ── Templates ───────────────────────────────────────────────────────────────


class TestTemplate:
    """Todo template tests."""

    def test_create_template(self, svc):
        """Create a basic template."""
        tpl = svc.create_template({"name": "Daily Standup"})
        assert tpl["uuid"] is not None
        assert tpl["name"] == "Daily Standup"
        assert tpl.get("fields") == []

    def test_create_template_with_fields(self, svc):
        """Create a template with fields."""
        tpl = svc.create_template({
            "name": "Weekly Report",
            "title_placeholder": "Report for week of ...",
            "fields": [
                {"name": "summary", "type": "text"},
                {"name": "!blockers", "type": "markdown"},  # ! prefix = required
            ],
        })
        assert tpl["name"] == "Weekly Report"
        assert tpl["title_placeholder"] == "Report for week of ..."
        assert len(tpl["fields"]) == 2
        # The ! prefix makes it required, field_name should be "blockers"
        fields_by_name = {f["field_name"]: f for f in tpl["fields"]}
        assert fields_by_name["summary"]["is_required"] == 0
        assert fields_by_name["blockers"]["is_required"] == 1
        assert fields_by_name["blockers"]["field_type"] == "markdown"

    def test_create_template_empty_name_raises(self, svc):
        """Creating a template with empty name raises ValueError."""
        with pytest.raises(ValueError, match="Template name is required"):
            svc.create_template({"name": ""})

    def test_get_template(self, svc):
        """Get a template by UUID."""
        tpl = svc.create_template({"name": "Sprint Review"})
        fetched = svc.get_template(tpl["uuid"])
        assert fetched is not None
        assert fetched["name"] == "Sprint Review"

    def test_get_template_nonexistent(self, svc):
        """Getting a non-existent template returns None."""
        assert svc.get_template("nonexistent") is None

    def test_get_template_by_name(self, svc):
        """Get a template by name."""
        svc.create_template({"name": "One-on-One"})
        fetched = svc.get_template_by_name("One-on-One")
        assert fetched is not None
        assert fetched["name"] == "One-on-One"

    def test_get_template_by_name_nonexistent(self, svc):
        """Getting a non-existent template by name returns None."""
        assert svc.get_template_by_name("Nope") is None

    def test_list_templates(self, svc):
        """List all templates."""
        svc.create_template({"name": "B Template"})
        svc.create_template({"name": "A Template"})
        templates = svc.list_templates()
        assert len(templates) == 2
        # Ordered by name ASC
        assert templates[0]["name"] == "A Template"
        assert templates[1]["name"] == "B Template"

    def test_list_templates_empty(self, svc):
        """List templates when none exist returns empty."""
        assert svc.list_templates() == []

    def test_update_template_name(self, svc):
        """Update a template's name."""
        tpl = svc.create_template({"name": "Old Name"})
        updated = svc.update_template(tpl["uuid"], {"name": "New Name"})
        assert updated["name"] == "New Name"

    def test_update_template_fields(self, svc):
        """Update a template's fields."""
        tpl = svc.create_template({
            "name": "Report",
            "fields": [{"name": "old_field", "type": "text"}],
        })
        updated = svc.update_template(tpl["uuid"], {
            "fields": [{"name": "new_field", "type": "markdown"}],
        })
        field_names = [f["field_name"] for f in updated["fields"]]
        assert "new_field" in field_names
        assert "old_field" not in field_names

    def test_delete_template(self, svc):
        """Delete a template."""
        tpl = svc.create_template({"name": "ToDelete"})
        svc.delete_template(tpl["uuid"])
        assert svc.get_template(tpl["uuid"]) is None

    def test_template_fields_in_use(self, svc):
        """template_fields_in_use reports field usage across todos."""
        tpl = svc.create_template({
            "name": "Bug Report",
            "fields": [{"name": "severity", "type": "text"}],
        })
        used = svc.template_fields_in_use(tpl["uuid"])
        # No todos use this template yet
        assert used == {}

    def test_template_fields_in_use_no_template(self, svc):
        """template_fields_in_use for non-existent template returns empty."""
        assert svc.template_fields_in_use("nonexistent") == {}


# ── Export / Import ─────────────────────────────────────────────────────────


class TestExportImport:
    """Markdown export and import tests."""

    def test_export_md_single(self, svc):
        """Export a single todo produces valid YAML frontmatter."""
        todo = svc.create({"title": "Export me", "priority": "2"})
        md = svc.export_md(uuid=todo["uuid"])
        assert "---" in md
        assert todo["uuid"] in md
        assert "domain: todo" in md
        assert "priority: '2'" in md or 'priority: "2"' in md
        assert f"## {todo['title']}" in md

    def test_export_md_with_labels(self, svc):
        """Export includes tags in frontmatter."""
        todo = svc.create({"title": "Tagged export", "_tags": ["bug", "blocker"]})
        md = svc.export_md(uuid=todo["uuid"])
        # Frontmatter should list tags
        assert "tags:" in md
        assert "bug" in md
        assert "blocker" in md

    def test_export_md_with_children(self, svc):
        """Export shows Children section for todos with children."""
        parent = svc.create({"title": "Parent"})
        child = svc.create({"title": "Child task", "parent_uuid": parent["uuid"]})
        md = svc.export_md(uuid=parent["uuid"])
        assert "### Children" in md
        assert "Child task" in md
        assert child["uuid"][:8] in md

    def test_export_md_multiple(self, svc):
        """Export multiple todos by uuids list."""
        t1 = svc.create({"title": "Task A"})
        t2 = svc.create({"title": "Task B"})
        md = svc.export_md(uuids=[t1["uuid"], t2["uuid"]])
        assert "Task A" in md
        assert "Task B" in md
        # Each entry has its own frontmatter
        assert md.count("---") >= 4  # 2 entries × 2 delimiters

    def test_export_md_all(self, svc):
        """Export all todos when no uuid/uuids given."""
        svc.create({"title": "All A"})
        svc.create({"title": "All B"})
        md = svc.export_md()
        assert "All A" in md
        assert "All B" in md

    def test_export_md_with_dependencies(self, svc):
        """Export shows Dependencies section."""
        dep = svc.create({"title": "Dependency"})
        todo = svc.create({
            "title": "Depends on",
            "_depends_on": [dep["uuid"]],
        })
        md = svc.export_md(uuid=todo["uuid"])
        assert "### Dependencies" in md
        assert dep["uuid"][:8] in md

    def test_import_md_creates_todo(self, svc, tmp_path):
        """Import markdown creates a todo entry."""
        md = (
            "---\n"
            "title: Imported Task\n"
            "domain: todo\n"
            "priority: '3'\n"
            "status: pending\n"
            "---\n"
            "\n"
            "## Imported Task\n"
            "\n"
            "Description text\n"
        )
        path = tmp_path / "import.md"
        path.write_text(md)
        uuids = svc.import_md(str(path))
        assert len(uuids) == 1
        todo = svc.get(uuids[0])
        assert todo["title"] == "Imported Task"
        assert todo["priority"] == "3"

    def test_import_md_with_tags(self, svc, tmp_path):
        """Import creates tags from frontmatter."""
        md = (
            "---\n"
            "title: Tagged Import\n"
            "tags:\n"
            "  - imported\n"
            "  - test\n"
            "---\n"
            "\n"
            "## Tagged Import\n"
        )
        path = tmp_path / "tags.md"
        path.write_text(md)
        uuids = svc.import_md(str(path))
        labels = svc.get_labels(uuids[0])
        label_names = [l["name"] for l in labels]
        assert "imported" in label_names
        assert "test" in label_names

    def test_import_md_with_dependencies(self, svc, tmp_path):
        """Import creates dependencies from frontmatter."""
        dep = svc.create({"title": "Existing dep"})
        md = (
            "---\n"
            f"title: Dependent Import\n"
            f"dependencies:\n"
            f"  - {dep['uuid']}\n"
            "---\n"
            "\n"
            "## Dependent Import\n"
        )
        path = tmp_path / "deps.md"
        path.write_text(md)
        uuids = svc.import_md(str(path))
        deps = svc.get_dependencies(uuids[0])
        assert len(deps) == 1
        assert deps[0]["uuid"] == dep["uuid"]

    def test_export_import_round_trip(self, svc, tmp_path):
        """Round-trip: export then import produces correct data."""
        # Create a todo with tags
        todo = svc.create({
            "title": "Round trip",
            "description": "Test description",
            "priority": "1",
        })
        # Export it
        md = svc.export_md(uuid=todo["uuid"])
        # Import it into a fresh service (reuse same svc, which is fine)
        path = tmp_path / "roundtrip.md"
        path.write_text(md)
        uuids = svc.import_md(str(path))
        imported = svc.get(uuids[0])
        assert imported is not None
        assert imported["title"] == "Round trip"
        assert imported["priority"] == "1"

    def test_import_md_malformed(self, svc, tmp_path):
        """Malformed frontmatter is handled gracefully (no entries)."""
        # Text without frontmatter delimiters produces no entries
        md = "Some random text without frontmatter"
        path = tmp_path / "malformed.md"
        path.write_text(md)
        uuids = svc.import_md(str(path))
        assert uuids == []  # No frontmatter = no entries

    def test_import_md_empty_file(self, svc, tmp_path):
        """Empty markdown file produces no entries."""
        path = tmp_path / "empty.md"
        path.write_text("")
        uuids = svc.import_md(str(path))
        assert uuids == []  # No frontmatter = no entries

    def test_import_md_no_title_in_frontmatter(self, svc, tmp_path):
        """Uses H2 heading when no title in frontmatter."""
        md = (
            "---\n"
            "priority: '1'\n"
            "---\n"
            "\n"
            "## H2 Title\n"
        )
        path = tmp_path / "h2title.md"
        path.write_text(md)
        uuids = svc.import_md(str(path))
        todo = svc.get(uuids[0])
        assert todo["title"] == "H2 Title"


# ── Search ──────────────────────────────────────────────────────────────────


class TestSearch:
    """Todo search tests."""

    def test_search_by_title(self, svc):
        """Search by title returns matching todos."""
        svc.create({"title": "Alpha task"})
        svc.create({"title": "Beta task"})
        results = svc.search("alpha")
        assert len(results) == 1
        assert results[0]["title"] == "Alpha task"

    def test_search_by_description(self, svc):
        """Search by description returns matching todos."""
        svc.create({"title": "Note", "description": "Important stuff"})
        results = svc.search("important")
        assert len(results) == 1

    def test_search_case_insensitive(self, svc):
        """Search is case-insensitive."""
        svc.create({"title": "UPPERCASE TASK"})
        results = svc.search("uppercase")
        assert len(results) == 1

    def test_search_no_match(self, svc):
        """Search with non-matching query returns empty."""
        svc.create({"title": "Hello"})
        results = svc.search("nonexistent")
        assert results == []

    def test_search_empty_query_returns_all(self, svc):
        """Empty query falls back to list (all todos)."""
        svc.create({"title": "A"})
        svc.create({"title": "B"})
        results = svc.search("")
        assert len(results) == 2

    def test_search_with_status_filter(self, svc):
        """Search filtered by status."""
        svc.create({"title": "Active task"})
        done = svc.create({"title": "Done task"})
        svc.mark_done(done["uuid"])
        results = svc.search("task", status="pending")
        assert len(results) == 1
        assert results[0]["title"] == "Active task"

    def test_search_with_tags(self, svc):
        """Search filtered by tags."""
        svc.create({"title": "Work task", "_tags": ["work"]})
        svc.create({"title": "Personal task", "_tags": ["personal"]})
        results = svc.search("task", tags=["work"])
        assert len(results) == 1
        assert results[0]["title"] == "Work task"

    def test_search_tags_must_match_all(self, svc):
        """Search with multiple tags requires all to match."""
        svc.create({"title": "Both", "_tags": ["work", "urgent"]})
        svc.create({"title": "Only work", "_tags": ["work"]})
        results = svc.search("", tags=["work", "urgent"])
        assert len(results) == 1
        assert results[0]["title"] == "Both"

    def test_search_respects_limit(self, svc):
        """Search respects the limit parameter."""
        for i in range(5):
            svc.create({"title": f"Task {i}"})
        results = svc.search("task", limit=2)
        assert len(results) == 2

    def test_search_short_query(self, svc):
        """Short queries (1 char) use LIKE fallback."""
        svc.create({"title": "Xylophone"})
        results = svc.search("x")
        assert len(results) == 1

    def test_search_with_sort(self, svc):
        """Search respects sort parameter."""
        svc.create({"title": "B task"})
        svc.create({"title": "A task"})
        results = svc.search("task", sort="title")
        assert len(results) == 2
        assert results[0]["title"] == "A task"
        assert results[1]["title"] == "B task"

    def test_search_attaches_labels(self, svc):
        """Search results include labels."""
        svc.create({"title": "Search label", "_tags": ["found"]})
        results = svc.search("search")
        assert len(results) == 1
        labels = results[0].get("labels", [])
        assert any(l["name"] == "found" for l in labels)

    def test_search_titles(self, svc):
        """search_titles returns only title and uuid."""
        svc.create({"title": "Autocomplete target"})
        results = svc.search_titles("auto")
        assert len(results) == 1
        assert results[0]["title"] == "Autocomplete target"
        assert "uuid" in results[0]

    def test_search_titles_empty_query(self, svc):
        """search_titles with empty query returns empty list."""
        svc.create({"title": "Whatever"})
        assert svc.search_titles("") == []

    def test_search_titles_no_match(self, svc):
        """search_titles with non-matching query returns empty."""
        assert svc.search_titles("zzzzz") == []


# ── Labels ──────────────────────────────────────────────────────────────────


class TestLabels:
    """Label management tests."""

    def test_add_label(self, svc):
        """Add a label to a todo."""
        todo = svc.create({"title": "Label target"})
        svc.add_label(todo["uuid"], "important")
        labels = svc.get_labels(todo["uuid"])
        assert len(labels) == 1
        assert labels[0]["name"] == "important"

    def test_add_label_idempotent(self, svc):
        """Adding the same label twice does not duplicate."""
        todo = svc.create({"title": "Dedup"})
        svc.add_label(todo["uuid"], "work")
        svc.add_label(todo["uuid"], "work")
        labels = svc.get_labels(todo["uuid"])
        assert len(labels) == 1

    def test_remove_label(self, svc):
        """Remove a label from a todo."""
        todo = svc.create({"title": "Remove label", "_tags": ["remove-me"]})
        svc.remove_label(todo["uuid"], "remove-me")
        labels = svc.get_labels(todo["uuid"])
        assert labels == []

    def test_list_all_labels(self, svc):
        """list_all_labels returns all defined labels."""
        svc.create_label({"name": "alpha"})
        svc.create_label({"name": "beta"})
        labels = svc.list_all_labels()
        assert len(labels) == 2
        label_names = [l["name"] for l in labels]
        assert "alpha" in label_names
        assert "beta" in label_names

    def test_list_all_labels_empty(self, svc):
        """list_all_labels returns empty when no labels exist."""
        assert svc.list_all_labels() == []

    def test_create_label(self, svc):
        """Create a label with name and color."""
        label = svc.create_label({"name": "urgent", "color": "#ff0000"})
        assert label["name"] == "urgent"
        assert label["color"] == "#ff0000"

    def test_create_label_duplicate_raises(self, svc):
        """Creating a duplicate label raises ValueError."""
        svc.create_label({"name": "unique"})
        with pytest.raises(ValueError, match="already exists"):
            svc.create_label({"name": "unique"})

    def test_create_label_empty_name_raises(self, svc):
        """Creating a label with empty name raises ValueError."""
        with pytest.raises(ValueError, match="Label name is required"):
            svc.create_label({"name": ""})

    def test_delete_label(self, svc):
        """Delete a label by name."""
        svc.create_label({"name": "delete-me"})
        svc.delete_label("delete-me")
        labels = svc.list_all_labels()
        assert len(labels) == 0

    def test_labels_on_todo_preserved_after_create_label(self, svc):
        """Labels attached via _tags survive after create_label is called."""
        todo = svc.create({"title": "Labeled", "_tags": ["mytag"]})
        # The label should already exist (created via _post_create → add_label)
        labels = svc.get_labels(todo["uuid"])
        assert len(labels) == 1
        assert labels[0]["name"] == "mytag"


# ── Dependencies ────────────────────────────────────────────────────────────


class TestDependencies:
    """Dependency management tests."""

    def test_add_dependency(self, svc):
        """Add a dependency between two todos."""
        t1 = svc.create({"title": "Task 1"})
        t2 = svc.create({"title": "Task 2"})
        svc.add_dependency(t2["uuid"], t1["uuid"])
        deps = svc.get_dependencies(t2["uuid"])
        assert len(deps) == 1
        assert deps[0]["uuid"] == t1["uuid"]

    def test_add_dependency_idempotent(self, svc):
        """Adding same dependency twice is idempotent."""
        t1 = svc.create({"title": "A"})
        t2 = svc.create({"title": "B"})
        svc.add_dependency(t2["uuid"], t1["uuid"])
        svc.add_dependency(t2["uuid"], t1["uuid"])
        deps = svc.get_dependencies(t2["uuid"])
        assert len(deps) == 1

    def test_add_self_dependency_raises(self, svc):
        """A task cannot depend on itself."""
        t = svc.create({"title": "Self"})
        with pytest.raises(ValueError, match="cannot depend on itself"):
            svc.add_dependency(t["uuid"], t["uuid"])

    def test_remove_dependency(self, svc):
        """Remove a dependency."""
        t1 = svc.create({"title": "A"})
        t2 = svc.create({"title": "B"})
        svc.add_dependency(t2["uuid"], t1["uuid"])
        svc.remove_dependency(t2["uuid"], t1["uuid"])
        deps = svc.get_dependencies(t2["uuid"])
        assert deps == []

    def test_get_dependencies_empty(self, svc):
        """Task with no dependencies returns empty list."""
        t = svc.create({"title": "Alone"})
        assert svc.get_dependencies(t["uuid"]) == []

    def test_get_blocked_tasks(self, svc):
        """get_blocked_tasks returns tasks blocked by a task."""
        t1 = svc.create({"title": "Blocking"})
        t2 = svc.create({"title": "Blocked"})
        svc.add_dependency(t2["uuid"], t1["uuid"])
        blocked = svc.get_blocked_tasks(t1["uuid"])
        assert len(blocked) == 1
        assert blocked[0]["uuid"] == t2["uuid"]

    def test_get_blocked_tasks_empty(self, svc):
        """Task blocking nothing returns empty."""
        t = svc.create({"title": "Not blocking"})
        assert svc.get_blocked_tasks(t["uuid"]) == []


# ── Priority ────────────────────────────────────────────────────────────────


class TestPriority:
    """Priority formula tests."""

    def test_computed_priority_basic(self, svc):
        """_computed_priority added by list/search, not by create."""
        svc.create({"title": "Static", "priority": "3"})
        fetched = svc.list()[0]
        assert fetched["_computed_priority"] == 3.0

    def test_validate_priority_formula_valid(self, svc):
        """Valid priority formula returns True."""
        assert svc.validate_priority_formula("5") is True
        assert svc.validate_priority_formula("min(20 + 5, 50)") is True
        assert svc.validate_priority_formula("max(1, D + 2)") is True

    def test_validate_priority_formula_invalid(self, svc):
        """Invalid priority formula returns False."""
        assert svc.validate_priority_formula("") is False
        assert svc.validate_priority_formula("__import__('os')") is False


# ── DB Schema ───────────────────────────────────────────────────────────────


class TestDB:
    """Database schema tests."""

    def test_get_db_creates_tables(self, tmp_path):
        """get_db creates all todo tables."""
        from lighterbird.todo.db import get_db

        db = get_db(tmp_path / "test_todo.db")
        assert db.table_exists("tasks")
        assert db.table_exists("labels")
        assert db.table_exists("todo_labels")
        assert db.table_exists("todo_dependencies")
        assert db.table_exists("attachments")
        assert db.table_exists("templates")
        assert db.table_exists("template_fields")

    def test_get_db_idempotent(self, tmp_path):
        """Calling get_db multiple times does not raise."""
        from lighterbird.todo.db import get_db

        path = tmp_path / "idemp.db"
        get_db(path)
        get_db(path)  # Should not raise

    def test_count_zero(self, svc):
        """Count returns 0 when no todos exist."""
        assert svc.count() == 0

    def test_count_after_create(self, svc):
        """Count reflects created todos."""
        svc.create({"title": "A"})
        svc.create({"title": "B"})
        assert svc.count() == 2

    def test_count_after_delete(self, svc):
        """Count decreases after delete."""
        t = svc.create({"title": "To count"})
        svc.delete(t["uuid"])
        assert svc.count() == 0


# ── Edge Cases ──────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_create_with_invalid_priority_string(self, svc):
        """Creating with a non-numeric priority sets _computed_priority to 5.0."""
        todo = svc.create({"title": "Bad priority", "priority": "abc"})
        # Computed should fallback to 5.0
        fetched = svc.list()[0]
        assert fetched["_computed_priority"] == 5.0

    def test_create_with_very_long_title(self, svc):
        """Very long title is handled."""
        long_title = "A" * 5000
        todo = svc.create({"title": long_title})
        assert len(todo["title"]) == 5000

    def test_list_with_sort_none(self, svc):
        """list with sort=None defaults to created_at DESC."""
        svc.create({"title": "First"})
        svc.create({"title": "Second"})
        results = svc.list(sort=None)
        assert len(results) == 2
        # Default is created_at DESC, so newest first
        assert results[0]["title"] == "Second"

    def test_search_with_query_and_status_and_tags(self, svc):
        """Search combines query, status, and tags filters."""
        todo = svc.create({"title": "Special project", "_tags": ["work"]})
        svc.create({"title": "Other work", "_tags": ["work"]})
        svc.mark_done(todo["uuid"])
        results = svc.search("project", status="done", tags=["work"])
        assert len(results) == 1
        assert results[0]["title"] == "Special project"

    def test_get_uuid_not_found(self, svc):
        """Getting a fake UUID returns None."""
        fake = _make_uuid()
        assert svc.get(fake) is None

    def test_delete_by_full_uuid(self, svc):
        """Delete by full UUID works."""
        todo = svc.create({"title": "Full delete"})
        svc.delete(todo["uuid"])
        assert svc.get(todo["uuid"]) is None

    def test_priority_computation_with_empty_created_at(self, svc):
        """priority computation handles missing created_at."""
        # We can't easily create a todo without created_at via CRUD,
        # but test the method directly
        assert svc._compute_priority({"priority": "5", "created_at": ""}) == 5.0

    def test_priority_computation_with_invalid_created_at(self, svc):
        """priority computation handles invalid created_at."""
        result = svc._compute_priority({"priority": "5", "created_at": "bad-date"})
        assert result == 5.0

    def test_priority_computation_with_none_priority(self, svc):
        """priority computation handles None priority."""
        result = svc._compute_priority({"priority": None, "created_at": ""})
        assert result == 5.0

    def test_flatten_tree_empty(self, svc):
        """flatten_tree with no todos returns empty."""
        assert svc.flatten_tree() == []

    def test_search_titles_no_results(self, svc):
        """search_titles with no match returns empty."""
        svc.create({"title": "Real task"})
        assert svc.search_titles("zzzzz") == []
