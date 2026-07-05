"""Tests for user_commands/service.py — CRUD + template expansion."""

from __future__ import annotations

import pytest

from lighterbird.user_commands.service import UserCommandsError, UserCommandsService


@pytest.fixture
def svc(monkeypatch, tmp_path):
    """Return a fresh UserCommandsService with isolated temp DB."""
    from lighterbird.user_commands import db as ucdb
    monkeypatch.setattr(ucdb, "_DB_PATH", tmp_path / "user_commands.db")
    ucdb.reset_db()
    return UserCommandsService()


class TestCreate:
    def test_create_minimal(self, svc):
        cmd = svc.create("myalias", "email list", hint="List emails")
        assert cmd["alias"] == "myalias"
        assert cmd["command_template"] == "email list"
        assert cmd["hint"] == "List emails"
        assert cmd["uuid"]

    def test_create_strips_leading_bang(self, svc):
        cmd = svc.create("test", "!email list")
        assert cmd["command_template"] == "email list"

    def test_create_duplicate_alias_raises(self, svc):
        svc.create("dup", "email list")
        with pytest.raises(UserCommandsError, match="already exists"):
            svc.create("dup", "other command")

    def test_create_empty_alias_raises(self, svc):
        with pytest.raises(UserCommandsError, match="cannot be empty"):
            svc.create("", "something")

    def test_create_empty_template_raises(self, svc):
        with pytest.raises(UserCommandsError, match="cannot be empty"):
            svc.create("test", "")

    def test_create_invalid_alias_raises(self, svc):
        with pytest.raises(UserCommandsError, match="Invalid alias"):
            svc.create("invalid alias!", "something")


class TestList:
    def test_list_empty(self, svc):
        assert svc.list_all() == []

    def test_list_returns_all(self, svc):
        svc.create("a", "cmd1")
        svc.create("b", "cmd2")
        all_cmds = svc.list_all()
        assert len(all_cmds) == 2
        assert all_cmds[0]["alias"] == "a"
        assert all_cmds[1]["alias"] == "b"

    def test_list_sorted_by_alias(self, svc):
        svc.create("z", "cmd")
        svc.create("a", "cmd")
        aliases = [c["alias"] for c in svc.list_all()]
        assert aliases == ["a", "z"]


class TestGetByAlias:
    def test_get_existing(self, svc):
        svc.create("testalias", "email list")
        cmd = svc.get_by_alias("testalias")
        assert cmd is not None
        assert cmd["command_template"] == "email list"

    def test_get_case_insensitive(self, svc):
        svc.create("MyAlias2", "email list")
        assert svc.get_by_alias("myalias2") is not None
        assert svc.get_by_alias("MYALIAS2") is not None

    def test_get_nonexistent(self, svc):
        assert svc.get_by_alias("nonexistent") is None


class TestUpdate:
    def test_update_template(self, svc):
        svc.create("testupd", "email list")
        updated = svc.update("testupd", command_template="email search")
        assert updated["command_template"] == "email search"

    def test_update_hint(self, svc):
        svc.create("testhint", "email list", hint="old hint")
        updated = svc.update("testhint", hint="new hint")
        assert updated["hint"] == "new hint"

    def test_update_rename(self, svc):
        svc.create("oldname", "email list")
        updated = svc.update("oldname", new_alias="newname")
        assert updated["alias"] == "newname"
        assert svc.get_by_alias("oldname") is None
        assert svc.get_by_alias("newname") is not None

    def test_update_nonexistent(self, svc):
        assert svc.update("nonexistent", command_template="x") is None


class TestDelete:
    def test_delete_existing(self, svc):
        svc.create("testdel", "email list")
        assert svc.delete("testdel") is True
        assert svc.get_by_alias("testdel") is None

    def test_delete_nonexistent(self, svc):
        assert svc.delete("nonexistent") is False


class TestTemplateExpansion:
    def test_expand_simple(self):
        result = UserCommandsService.expand_template("email list --folder $1", ["INBOX"])
        assert result == "email list --folder INBOX"

    def test_expand_multiple_args(self):
        result = UserCommandsService.expand_template(
            "email send $1 $2", ["to@b.com", "Subject"]
        )
        assert result == "email send to@b.com Subject"

    def test_expand_no_placeholders(self):
        result = UserCommandsService.expand_template("email list", ["extra"])
        assert result == "email list"

    def test_expand_partial(self):
        result = UserCommandsService.expand_template(
            "email send $1 Test", ["to@b.com"]
        )
        assert result == "email send to@b.com Test"
