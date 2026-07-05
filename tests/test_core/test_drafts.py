"""Tests for lighterbird.core.drafts — per-domain draft storage.

Covers: list_drafts, get_draft, save_draft, delete_draft,
delete_drafts_by_domain, cleanup_old_drafts, and edge cases.

Data directory isolation is provided by the root conftest's
autouse ``auto_isolate_data_dir`` fixture.
"""

from __future__ import annotations

import json
from datetime import UTC
from pathlib import Path

import pytest

from lighterbird.core.drafts import (
    cleanup_old_drafts,
    delete_draft,
    delete_drafts_by_domain,
    get_draft,
    list_drafts,
    save_draft,
)
from lighterbird.core.paths import data_dir


class TestSaveDraft:
    def test_create_new(self):
        draft = save_draft("email", "Test Draft", {"to": "a@b.com"})
        assert draft["uuid"] is not None
        assert draft["domain"] == "email"
        assert draft["title"] == "Test Draft"
        assert draft["data"]["to"] == "a@b.com"
        assert "created_at" in draft
        assert "updated_at" in draft

    def test_create_all_domains(self):
        for domain in ["email", "journal", "todo", "calendar-event", "letter"]:
            draft = save_draft(domain, f"Test {domain}", {})
            assert draft["domain"] == domain

    def test_invalid_domain_raises(self):
        with pytest.raises(ValueError, match="Invalid domain"):
            save_draft("invalid_domain", "Bad", {})

    def test_update_existing(self):
        draft = save_draft("email", "Original", {"to": "a@b.com"})
        updated = save_draft("email", "Updated", {"to": "new@b.com"}, draft_uuid=draft["uuid"])
        assert updated["uuid"] == draft["uuid"]
        assert updated["title"] == "Updated"
        assert updated["data"]["to"] == "new@b.com"
        loaded = get_draft(draft["uuid"])
        assert loaded is not None
        assert loaded["title"] == "Updated"

    def test_update_nonexistent_uuid_creates_new(self):
        draft = save_draft("email", "Fallback", {}, draft_uuid="nonexistent-uuid")
        assert draft["uuid"] != "nonexistent-uuid"

    def test_multiple_drafts(self):
        save_draft("email", "D1", {})
        save_draft("journal", "D2", {})
        save_draft("email", "D3", {})
        assert len(list_drafts()) == 3


class TestListDrafts:
    def test_list_all(self):
        save_draft("email", "E1", {})
        save_draft("journal", "J1", {})
        save_draft("todo", "T1", {})
        assert len(list_drafts()) == 3

    def test_list_by_domain(self):
        save_draft("email", "E1", {})
        save_draft("email", "E2", {})
        save_draft("journal", "J1", {})
        email_drafts = list_drafts("email")
        assert len(email_drafts) == 2
        assert all(d["domain"] == "email" for d in email_drafts)

    def test_list_by_domain_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid domain"):
            list_drafts("bad_domain")

    def test_list_empty(self):
        assert list_drafts() == []

    def test_list_returns_newest_first(self):
        d1 = save_draft("email", "Old", {})
        d2 = save_draft("email", "New", {})
        result = list_drafts()
        assert result[0]["uuid"] == d2["uuid"]
        assert result[1]["uuid"] == d1["uuid"]

    def test_list_empty_domain(self):
        save_draft("email", "E1", {})
        assert list_drafts("todo") == []


class TestGetDraft:
    def test_get_existing(self):
        draft = save_draft("email", "Test", {})
        found = get_draft(draft["uuid"])
        assert found is not None
        assert found["uuid"] == draft["uuid"]

    def test_get_nonexistent(self):
        assert get_draft("nonexistent-uuid") is None

    def test_get_after_delete(self):
        draft = save_draft("email", "Test", {})
        delete_draft(draft["uuid"])
        assert get_draft(draft["uuid"]) is None


class TestDeleteDraft:
    def test_delete_existing(self):
        draft = save_draft("email", "Test", {})
        assert delete_draft(draft["uuid"]) is True
        assert list_drafts() == []

    def test_delete_nonexistent(self):
        assert delete_draft("nonexistent-uuid") is False

    def test_delete_only_one(self):
        d1 = save_draft("email", "D1", {})
        d2 = save_draft("email", "D2", {})
        delete_draft(d1["uuid"])
        remaining = list_drafts()
        assert len(remaining) == 1
        assert remaining[0]["uuid"] == d2["uuid"]


class TestDeleteDraftsByDomain:
    def test_delete_domain(self):
        save_draft("email", "E1", {})
        save_draft("email", "E2", {})
        save_draft("journal", "J1", {})
        count = delete_drafts_by_domain("email")
        assert count == 2
        assert len(list_drafts()) == 1

    def test_delete_nonexistent_domain(self):
        save_draft("email", "E1", {})
        count = delete_drafts_by_domain("todo")
        assert count == 0
        assert len(list_drafts()) == 1

    def test_invalid_domain_raises(self):
        with pytest.raises(ValueError, match="Invalid domain"):
            delete_drafts_by_domain("bad_domain")


class TestCleanupOldDrafts:
    def test_cleanup_deletes_old_drafts(self):
        """cleanup_old_drafts should delete drafts older than max_age_days."""
        from datetime import datetime, timedelta

        draft = save_draft("email", "Old", {})

        # Manually rewrite its updated_at to be 60 days ago
        old_ts = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        path = data_dir() / ".drafts.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for d in data:
            if d["uuid"] == draft["uuid"]:
                d["updated_at"] = old_ts
                d["created_at"] = old_ts
        path.write_text(json.dumps(data), encoding="utf-8")

        deleted = cleanup_old_drafts(max_age_days=30)
        assert deleted == 1
        assert list_drafts() == []

    def test_cleanup_keeps_recent_drafts(self):
        save_draft("email", "Recent", {})
        deleted = cleanup_old_drafts(max_age_days=30)
        assert deleted == 0
        assert len(list_drafts()) == 1

    def test_cleanup_empty(self):
        assert cleanup_old_drafts() == 0

    def test_cleanup_parses_bad_timestamp(self):
        """Drafts with unparseable timestamps should be treated as old."""
        draft = save_draft("email", "Bad TS", {})
        path = data_dir() / ".drafts.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for d in data:
            if d["uuid"] == draft["uuid"]:
                d["updated_at"] = "not-a-timestamp"
        path.write_text(json.dumps(data), encoding="utf-8")

        deleted = cleanup_old_drafts(max_age_days=1)
        assert deleted == 1


class TestCorruptedJson:
    def test_corrupted_drafts_file_returns_empty_list(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LIGHTERBIRD_DATA_DIR", str(tmp_path))
        from lighterbird.server.deps import reset_services
        reset_services()
        drafts_file = tmp_path / ".drafts.json"
        drafts_file.write_text("{invalid json", encoding="utf-8")
        assert list_drafts() == []

    def test_save_recovery_after_corruption(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LIGHTERBIRD_DATA_DIR", str(tmp_path))
        from lighterbird.server.deps import reset_services
        reset_services()
        drafts_file = tmp_path / ".drafts.json"
        drafts_file.write_text("{invalid json", encoding="utf-8")
        draft = save_draft("email", "Recovery", {})
        assert get_draft(draft["uuid"]) is not None
