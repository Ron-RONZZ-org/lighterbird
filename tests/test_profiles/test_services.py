"""Tests for profiles/services/profiles.py — identity profile CRUD."""

from __future__ import annotations

import pytest

from lighterbird.profiles.services.profiles import ProfileError, ProfileService


@pytest.fixture
def svc(monkeypatch, tmp_path):
    """Return a fresh ProfileService with isolated temp DB."""
    from lighterbird.profiles import db as pdb
    monkeypatch.setattr(pdb, "_DB_PATH", tmp_path / "profiles.db")
    pdb.reset_db()
    return ProfileService()


class TestCreate:
    def test_create_minimal(self, svc):
        profile = svc.create({"profile_name": "work", "given_name": "Alice"})
        assert profile["given_name"] == "Alice"
        assert profile["full_name"] == "Alice"
        assert profile["uuid"]
        assert profile["profile_name"] == "work"

    def test_create_full_name_computed(self, svc):
        profile = svc.create({
            "profile_name": "personal",
            "given_name": "John",
            "middle_names": "M",
            "family_name": "Doe",
        })
        assert profile["full_name"] == "John M Doe"

    def test_create_validates_json_fields(self, svc):
        with pytest.raises(ProfileError, match="Invalid JSON"):
            svc.create({"profile_name": "x", "given_name": "A", "emails": "not-json"})

    def test_create_accepts_valid_json(self, svc):
        profile = svc.create({
            "profile_name": "x",
            "given_name": "A",
            "emails": '[{"value": "a@b.com"}]',
        })
        assert profile["emails"] == '[{"value": "a@b.com"}]'


class TestGetPrimaryEmail:
    def test_get_primary_email(self):
        data = {"emails": '[{"value": "a@b.com"}, {"value": "c@d.com"}]'}
        assert ProfileService.get_primary_email(data) == "a@b.com"

    def test_get_primary_email_empty(self):
        assert ProfileService.get_primary_email({"emails": "[]"}) == ""

    def test_get_primary_email_no_key(self):
        assert ProfileService.get_primary_email({}) == ""

    def test_get_primary_email_invalid_json(self):
        assert ProfileService.get_primary_email({"emails": "bad"}) == ""


class TestGetPrimaryPhone:
    def test_get_primary_phone(self):
        data = {"phones": '[{"value": "+1-555"}]'}
        assert ProfileService.get_primary_phone(data) == "+1-555"

    def test_get_primary_phone_empty(self):
        assert ProfileService.get_primary_phone({}) == ""


class TestList:
    def test_list_empty(self, svc):
        assert svc.list() == []

    def test_list_returns_all(self, svc):
        svc.create({"profile_name": "a", "given_name": "Alice"})
        svc.create({"profile_name": "b", "given_name": "Bob"})
        profiles = svc.list()
        assert len(profiles) == 2

    def test_list_includes_primary_email(self, svc):
        svc.create({
            "profile_name": "x",
            "given_name": "Alice",
            "emails": '[{"value": "alice@b.com"}]',
        })
        profiles = svc.list()
        assert profiles[0]["_primary_email"] == "alice@b.com"


class TestUpdate:
    def test_update_fields(self, svc):
        profile = svc.create({"profile_name": "w", "given_name": "Alice"})
        updated = svc.update(profile["uuid"], {"given_name": "Alicia"})
        assert updated["given_name"] == "Alicia"

    def test_update_recomputes_full_name(self, svc):
        profile = svc.create({"profile_name": "w", "given_name": "Alice"})
        updated = svc.update(profile["uuid"], {"family_name": "Smith"})
        assert updated["full_name"] == "Alice Smith"

    def test_update_nonexistent_returns_none(self, svc):
        result = svc.update("nonexistent-uuid", {"given_name": "X"})
        assert result is None
