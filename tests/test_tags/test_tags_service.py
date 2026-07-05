"""Tests for tags/service.py — TagService CRUD and taggings management."""

from __future__ import annotations

import pytest

from lighterbird.tags.db import get_db
from lighterbird.tags.service import TagService


@pytest.fixture
def svc(tmp_path):
    """Return a fresh TagService with isolated temp DB."""
    db = get_db(tmp_path / "tags.db")
    return TagService(db)


class TestCreateTag:
    def test_create_minimal(self, svc):
        tag = svc.create_tag("urgent")
        assert tag["name"] == "urgent"
        assert tag["color"] == ""
        assert tag.get("created_at")
        assert tag.get("updated_at")

    def test_create_with_color(self, svc):
        tag = svc.create_tag("important", color="#ff4444")
        assert tag["name"] == "important"
        assert tag["color"] == "#ff4444"

    def test_create_duplicate_raises(self, svc):
        svc.create_tag("urgent")
        with pytest.raises(ValueError, match="already exists"):
            svc.create_tag("urgent")

    def test_create_case_insensitive_collision(self, svc):
        svc.create_tag("Urgent")
        with pytest.raises(ValueError, match="already exists"):
            svc.create_tag("urgent")

    def test_empty_name_raises(self, svc):
        with pytest.raises(ValueError, match="Tag name is required"):
            svc.create_tag("")

    def test_whitespace_name_stripped_and_raises(self, svc):
        with pytest.raises(ValueError, match="Tag name is required"):
            svc.create_tag("   ")


class TestListTags:
    def test_empty_list(self, svc):
        assert svc.list_tags() == []

    def test_returns_all_tags_ordered(self, svc):
        svc.create_tag("bravo")
        svc.create_tag("alpha")
        svc.create_tag("charlie")
        tags = svc.list_tags()
        assert [t["name"] for t in tags] == ["alpha", "bravo", "charlie"]

    def test_single_tag(self, svc):
        svc.create_tag("only")
        tags = svc.list_tags()
        assert len(tags) == 1
        assert tags[0]["name"] == "only"


class TestRenameTag:
    def test_rename_success(self, svc):
        svc.create_tag("old")
        renamed = svc.rename_tag("old", "new")
        assert renamed["name"] == "new"
        assert svc.list_tags()[0]["name"] == "new"

    def test_rename_nonexistent_raises(self, svc):
        with pytest.raises(ValueError, match="not found"):
            svc.rename_tag("ghost", "alive")

    def test_rename_to_existing_raises(self, svc):
        svc.create_tag("existing")
        svc.create_tag("target")
        with pytest.raises(ValueError, match="already exists"):
            svc.rename_tag("existing", "target")

    def test_rename_empty_new_name_raises(self, svc):
        svc.create_tag("t")
        with pytest.raises(ValueError, match="New tag name is required"):
            svc.rename_tag("t", "")

    def test_rename_updates_taggings(self, svc):
        """Renaming a tag should preserve taggings."""
        svc.create_tag("old")
        svc.add_tag("todo", "item-001", "old")
        svc.rename_tag("old", "new")
        tags = svc.get_tags_for("todo", "item-001")
        assert len(tags) == 1
        assert tags[0]["name"] == "new"


class TestDeleteTag:
    def test_delete_existing(self, svc):
        svc.create_tag("remove-me")
        svc.delete_tag("remove-me")
        assert svc.list_tags() == []

    def test_delete_nonexistent_raises(self, svc):
        with pytest.raises(ValueError, match="not found"):
            svc.delete_tag("ghost")

    def test_delete_cascades_taggings(self, svc):
        svc.create_tag("todelete")
        svc.add_tag("todo", "item-001", "todelete")
        svc.delete_tag("todelete")
        tags = svc.get_tags_for("todo", "item-001")
        assert tags == []


class TestGetTagsFor:
    def test_no_tags(self, svc):
        assert svc.get_tags_for("todo", "nonexistent") == []

    def test_returns_tags_for_item(self, svc):
        svc.add_tag("todo", "item-001", "urgent")
        svc.add_tag("todo", "item-001", "work")
        tags = svc.get_tags_for("todo", "item-001")
        assert len(tags) == 2
        names = {t["name"] for t in tags}
        assert names == {"urgent", "work"}

    def test_other_item_not_included(self, svc):
        svc.add_tag("todo", "item-001", "urgent")
        svc.add_tag("todo", "item-002", "work")
        tags = svc.get_tags_for("todo", "item-001")
        assert len(tags) == 1
        assert tags[0]["name"] == "urgent"


class TestAddTag:
    def test_add_new_tag_auto_creates(self, svc):
        svc.add_tag("todo", "item-001", "newtag")
        tags = svc.list_tags()
        assert len(tags) == 1
        assert tags[0]["name"] == "newtag"

    def test_add_existing_tag_is_idempotent(self, svc):
        svc.add_tag("todo", "item-001", "urgent")
        svc.add_tag("todo", "item-001", "urgent")
        tags = svc.get_tags_for("todo", "item-001")
        assert len(tags) == 1

    def test_add_same_tag_different_items(self, svc):
        svc.add_tag("todo", "item-001", "urgent")
        svc.add_tag("todo", "item-002", "urgent")
        assert len(svc.get_tags_for("todo", "item-001")) == 1
        assert len(svc.get_tags_for("todo", "item-002")) == 1
        assert len(svc.list_tags()) == 1

    def test_add_tag_different_domains(self, svc):
        svc.add_tag("todo", "item-001", "urgent")
        svc.add_tag("journal", "entry-001", "urgent")
        assert len(svc.get_tags_for("todo", "item-001")) == 1
        assert len(svc.get_tags_for("journal", "entry-001")) == 1


class TestRemoveTag:
    def test_remove_existing(self, svc):
        svc.add_tag("todo", "item-001", "urgent")
        svc.remove_tag("todo", "item-001", "urgent")
        assert svc.get_tags_for("todo", "item-001") == []

    def test_remove_nonexistent_does_not_raise(self, svc):
        svc.remove_tag("todo", "ghost", "notag")  # should not raise

    def test_remove_other_tag_not_affected(self, svc):
        svc.add_tag("todo", "item-001", "urgent")
        svc.add_tag("todo", "item-001", "work")
        svc.remove_tag("todo", "item-001", "urgent")
        tags = svc.get_tags_for("todo", "item-001")
        assert len(tags) == 1
        assert tags[0]["name"] == "work"


class TestSetTags:
    def test_set_tags_replaces_all(self, svc):
        svc.add_tag("todo", "item-001", "old")
        svc.set_tags("todo", "item-001", ["new1", "new2"])
        tags = svc.get_tags_for("todo", "item-001")
        assert len(tags) == 2
        assert {t["name"] for t in tags} == {"new1", "new2"}

    def test_set_tags_removes_stale(self, svc):
        svc.add_tag("todo", "item-001", "stale")
        svc.add_tag("todo", "item-001", "keep")
        svc.set_tags("todo", "item-001", ["keep"])
        tags = svc.get_tags_for("todo", "item-001")
        assert len(tags) == 1
        assert tags[0]["name"] == "keep"

    def test_set_tags_empty_removes_all(self, svc):
        svc.add_tag("todo", "item-001", "some")
        svc.set_tags("todo", "item-001", [])
        assert svc.get_tags_for("todo", "item-001") == []

    def test_set_tags_creates_new_auto(self, svc):
        svc.set_tags("todo", "item-001", ["brand-new"])
        tags = svc.get_tags_for("todo", "item-001")
        assert len(tags) == 1
        assert tags[0]["name"] == "brand-new"

    def test_set_tags_idempotent(self, svc):
        svc.set_tags("todo", "item-001", ["urgent"])
        svc.set_tags("todo", "item-001", ["urgent"])
        assert len(svc.get_tags_for("todo", "item-001")) == 1


class TestListTagsForDomain:
    def test_empty_domain(self, svc):
        assert svc.list_tags_for_domain("todo") == []

    def test_lists_tags_with_usage_count(self, svc):
        svc.add_tag("todo", "item-001", "urgent")
        svc.add_tag("todo", "item-002", "urgent")
        svc.add_tag("todo", "item-001", "work")
        result = svc.list_tags_for_domain("todo")
        assert len(result) == 2
        counts = {r["name"]: r["usage_count"] for r in result}
        assert counts["urgent"] == 2
        assert counts["work"] == 1

    def test_tags_used_elsewhere_excluded(self, svc):
        svc.add_tag("todo", "item-001", "urgent")
        svc.add_tag("journal", "entry-001", "urgent")
        result = svc.list_tags_for_domain("journal")
        assert len(result) == 1
        assert result[0]["usage_count"] == 1

    def test_tags_ordered_by_name(self, svc):
        svc.add_tag("todo", "item-001", "zeta")
        svc.add_tag("todo", "item-002", "alpha")
        result = svc.list_tags_for_domain("todo")
        assert [r["name"] for r in result] == ["alpha", "zeta"]
