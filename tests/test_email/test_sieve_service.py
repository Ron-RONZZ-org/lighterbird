"""Tests for email/services/sieve.py — SieveService CRUD and activation."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lighterbird.email.services.sieve import SieveService

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    db = MagicMock()
    # Make execute return an empty list by default (iterable)
    db.execute.return_value = []
    db.execute_one.return_value = None
    return db


@pytest.fixture
def sieve(mock_db):
    return SieveService(mock_db)


# ── Helpers ──────────────────────────────────────────────────────────────────


class TestSieveServiceHelpers:
    def test_now_returns_iso(self):
        ts = SieveService._now()
        assert "T" in ts
        assert ts.endswith("Z") or "+" in ts or "-" in ts[10:]

    def test_validate_name_rejects_system_prefix(self, sieve):
        with pytest.raises(ValueError, match="reserved for system"):
            sieve._validate_name("_test")

    def test_validate_name_accepts_normal(self, sieve):
        sieve._validate_name("my-script")  # Should not raise

    def test_validate_name_accepts_underscore_non_prefix(self, sieve):
        sieve._validate_name("my_script")  # Should not raise

    def test_resolve_account_by_email(self, sieve, mock_db):
        mock_db.execute_one.return_value = {
            "email": "user@example.com",
            "managesieve_host": "sieve.example.com",
            "managesieve_port": 4190,
            "managesieve_use_tls": 1,
        }
        result = sieve._resolve_account("user@example.com")
        assert result is not None
        assert result["email"] == "user@example.com"

    def test_resolve_account_empty(self, sieve):
        assert sieve._resolve_account("") is None

    def test_resolve_account_none(self, sieve):
        assert sieve._resolve_account(None) is None

    def test_get_managesieve_config(self, sieve, mock_db):
        mock_db.execute_one.return_value = {
            "managesieve_host": "sieve.example.com",
            "managesieve_port": 4190,
            "managesieve_use_tls": 1,
        }
        cfg = sieve._get_managesieve_config("user@example.com")
        assert cfg is not None
        assert cfg["host"] == "sieve.example.com"

    def test_get_managesieve_config_no_host(self, sieve, mock_db):
        mock_db.execute_one.return_value = {
            "managesieve_host": "",
            "managesieve_port": 4190,
            "managesieve_use_tls": 1,
        }
        cfg = sieve._get_managesieve_config("user@example.com")
        assert cfg is None


# ── Script CRUD ──────────────────────────────────────────────────────────────


class TestCreateScript:
    def test_create_basic(self, sieve, mock_db):
        mock_db.execute_one.return_value = {
            "name": "test-filter", "content": 'require ["fileinto"];\nfileinto "INBOX";',
            "system": 0, "created_at": "now", "updated_at": "now",
        }
        script = sieve.create_script(
            "test-filter",
            content='require ["fileinto"];\nfileinto "INBOX";',
        )
        assert script["name"] == "test-filter"

    def test_create_system_prefix_raises(self, sieve):
        with pytest.raises(ValueError, match="reserved for system"):
            sieve.create_script("_system_script", content="")

    def test_create_duplicate_raises(self, sieve, mock_db):
        mock_db.execute.side_effect = Exception("UNIQUE constraint failed")
        with pytest.raises(ValueError, match="already exists"):
            sieve.create_script("exists", content="")


class TestListScripts:
    def test_list_no_account(self, sieve, mock_db):
        mock_db.execute.return_value = []
        scripts = sieve.list_scripts()
        assert scripts == []

    def test_list_with_account(self, sieve, mock_db):
        mock_db.execute.return_value = [
            {"name": "filter1", "content": "content1", "system": 0,
             "created_at": "now", "updated_at": "now",
             "akt_active": None, "akt_priority": None,
             "akt_man_sync": None, "akt_created_at": None, "akt_updated_at": None},
        ]
        scripts = sieve.list_scripts(account_email="user@example.com")
        assert len(scripts) == 1
        assert scripts[0]["name"] == "filter1"


class TestGetScript:
    def test_get_existing(self, sieve, mock_db):
        mock_db.execute_one.return_value = {
            "name": "test", "content": "content", "system": 0,
            "created_at": "now", "updated_at": "now",
        }
        script = sieve.get_script("test")
        assert script is not None
        assert script["name"] == "test"

    def test_get_nonexistent(self, sieve, mock_db):
        mock_db.execute_one.return_value = None
        assert sieve.get_script("nonexistent") is None

    def test_get_spam_blocks_returns_none(self, sieve):
        assert sieve.get_script("_spam_blocks") is None


class TestGetScriptWithActivation:
    def test_get_with_activation(self, sieve, mock_db):
        mock_db.execute_one.return_value = {
            "name": "test", "content": "content", "system": 0,
            "created_at": "now", "updated_at": "now",
            "akt_active": 1, "akt_priority": 0, "akt_man_sync": 1,
            "akt_created_at": "now", "akt_updated_at": "now",
        }
        script = sieve.get_script_with_activation("test", "user@example.com")
        assert script is not None
        assert script["aktivado"] is not None
        assert script["aktivado"]["active"] is True

    def test_get_without_activation(self, sieve, mock_db):
        mock_db.execute_one.return_value = {
            "name": "test", "content": "content", "system": 0,
            "created_at": "now", "updated_at": "now",
            "akt_active": None, "akt_priority": None, "akt_man_sync": None,
            "akt_created_at": None, "akt_updated_at": None,
        }
        script = sieve.get_script_with_activation("test", "user@example.com")
        assert script is not None
        assert script["aktivado"] is None


class TestUpdateScript:
    def test_update_content(self, sieve, mock_db):
        mock_db.execute_one.side_effect = [
            {"name": "test", "content": "old", "system": 0,
             "created_at": "now", "updated_at": "now"},
            {"name": "test", "content": "new require [\"fileinto\"];\nfileinto \"X\";", "system": 0,
             "created_at": "now", "updated_at": "now"},
        ]
        result = sieve.update_script("test", content='require ["fileinto"];\nfileinto "X";')
        assert result is not None
        assert result["name"] == "test"

    def test_update_rename(self, sieve, mock_db):
        mock_db.execute_one.side_effect = [
            {"name": "old-name", "content": "content", "system": 0,
             "created_at": "now", "updated_at": "now"},
            {"name": "new-name", "content": "content", "system": 0,
             "created_at": "now", "updated_at": "now"},
        ]
        result = sieve.update_script("old-name", new_name="new-name")
        assert result is not None
        assert result["name"] == "new-name"

    def test_update_nonexistent(self, sieve, mock_db):
        mock_db.execute_one.return_value = None
        assert sieve.update_script("nonexistent", content="blah") is None

    def test_update_system_script_raises(self, sieve, mock_db):
        mock_db.execute_one.return_value = {
            "name": "_system", "content": "", "system": 1,
            "created_at": "now", "updated_at": "now",
        }
        with pytest.raises(ValueError, match="read-only"):
            sieve.update_script("_system", content="new")


class TestDeleteScript:
    def test_delete_existing(self, sieve, mock_db):
        mock_db.execute_one.return_value = {
            "name": "test", "content": "", "system": 0,
            "created_at": "now", "updated_at": "now",
        }
        assert sieve.delete_script("test") is True

    def test_delete_nonexistent(self, sieve, mock_db):
        mock_db.execute_one.return_value = None
        assert sieve.delete_script("nonexistent") is False

    def test_delete_system_raises(self, sieve, mock_db):
        mock_db.execute_one.return_value = {
            "name": "_system", "content": "", "system": 1,
            "created_at": "now", "updated_at": "now",
        }
        with pytest.raises(ValueError, match="read-only"):
            sieve.delete_script("_system")


# ── Activation management ────────────────────────────────────────────────────


class TestActivateScript:
    def test_activate(self, sieve, mock_db):
        mock_db.execute_one.side_effect = [
            {"name": "filter1", "content": "content", "system": 0,
             "created_at": "now", "updated_at": "now"},  # get_script
            None,  # existing activation check → None (new)
            {"name": "filter1", "content": "content", "system": 0,
             "created_at": "now", "updated_at": "now",
             "akt_active": 1, "akt_priority": 0, "akt_man_sync": 1,
             "akt_created_at": "now", "akt_updated_at": "now"},  # result
        ]
        result = sieve.activate_script("filter1", "user@example.com")
        assert result is not None
        assert result["aktivado"]["active"] is True

    def test_activate_nonexistent(self, sieve, mock_db):
        mock_db.execute_one.return_value = None
        assert sieve.activate_script("nonexistent", "user@example.com") is None

    def test_activate_existing_updates(self, sieve, mock_db):
        mock_db.execute_one.side_effect = [
            {"name": "filter1", "content": "content", "system": 0,
             "created_at": "now", "updated_at": "now"},  # get_script
            {"1": 1},  # existing activation
            {"name": "filter1", "content": "content", "system": 0,
             "created_at": "now", "updated_at": "now",
             "akt_active": 1, "akt_priority": 5, "akt_man_sync": 0,
             "akt_created_at": "now", "akt_updated_at": "now"},
        ]
        result = sieve.activate_script("filter1", "user@example.com", priority=5, man_sync=False)
        assert result is not None


class TestDeactivateScript:
    def test_deactivate(self, sieve, mock_db):
        mock_db.execute_one.side_effect = [
            {"name": "filter1", "content": "content", "system": 0,
             "created_at": "now", "updated_at": "now"},  # get_script
            {"man_sync": 0},  # activation
        ]
        result = sieve.deactivate_script("filter1", "user@example.com")
        assert result is not None
        assert result["aktivado"] is None

    def test_deactivate_nonexistent(self, sieve, mock_db):
        mock_db.execute_one.return_value = None
        assert sieve.deactivate_script("nonexistent", "user@example.com") is None


class TestSetPriority:
    def test_set_priority(self, sieve, mock_db):
        mock_db.execute_one.return_value = {
            "name": "filter1", "content": "content", "system": 0,
            "created_at": "now", "updated_at": "now",
            "akt_active": 1, "akt_priority": 10, "akt_man_sync": 1,
            "akt_created_at": "now", "akt_updated_at": "now",
        }
        result = sieve.set_priority("filter1", "user@example.com", 10)
        assert result is not None


class TestActivateAll:
    def test_activate_all(self, sieve, mock_db):
        # Use side_effect for execute to return accounts first, then empty for other calls
        call_count = {"execute": 0}
        def execute_side_effect(*args, **kwargs):
            call_count["execute"] += 1
            # First call: fetch accounts with ManageSieve
            if call_count["execute"] == 1:
                return [
                    {"email": "a@example.com"},
                    {"email": "b@example.com"},
                ]
            # Subsequent execute calls (from _combine_and_sync) return empty
            return []
        mock_db.execute.side_effect = execute_side_effect

        mock_db.execute_one.side_effect = [
            {"name": "global-filter", "content": "", "system": 0,
             "created_at": "now", "updated_at": "now"},
            None,
            {"name": "global-filter", "content": "", "system": 0,
             "created_at": "now", "updated_at": "now",
             "akt_active": 1, "akt_priority": 0, "akt_man_sync": 1,
             "akt_created_at": "now", "akt_updated_at": "now"},
            {"name": "global-filter", "content": "", "system": 0,
             "created_at": "now", "updated_at": "now"},
            None,
            {"name": "global-filter", "content": "", "system": 0,
             "created_at": "now", "updated_at": "now",
             "akt_active": 1, "akt_priority": 0, "akt_man_sync": 1,
             "akt_created_at": "now", "akt_updated_at": "now"},
        ]
        result = sieve.activate_all("global-filter")
        assert len(result["succeeded"]) == 2


class TestDeactivateAll:
    def test_deactivate_all(self, sieve, mock_db):
        mock_db.execute.return_value = [
            {"account_email": "a@example.com"},
            {"account_email": "b@example.com"},
        ]
        mock_db.execute_one.side_effect = [
            {"name": "global-filter", "content": "", "system": 0,
             "created_at": "now", "updated_at": "now"},
            {"man_sync": 0},
            {"name": "global-filter", "content": "", "system": 0,
             "created_at": "now", "updated_at": "now"},
            {"man_sync": 0},
        ]
        result = sieve.deactivate_all("global-filter")
        assert len(result["succeeded"]) == 2

    def test_deactivate_all_no_activations(self, sieve, mock_db):
        mock_db.execute.return_value = []
        result = sieve.deactivate_all("global-filter")
        assert result == {"succeeded": [], "failed": []}


class TestListActivations:
    def test_list_activations(self, sieve, mock_db):
        mock_db.execute.return_value = [
            {"script_name": "filter1", "account_email": "user@example.com",
             "active": 1, "priority": 0, "man_sync": 1,
             "created_at": "now", "updated_at": "now",
             "script_content": "content", "script_system": 0},
        ]
        result = sieve.list_activations("user@example.com")
        assert len(result) == 1
        assert result[0]["script_name"] == "filter1"


class TestUpsertSpamBlocks:
    def test_upsert_spam_blocks_noop(self, sieve):
        result = sieve.upsert_spam_blocks("user@example.com", "content")
        assert result["name"] == "_spam_blocks"
        assert result["content"] == "content"


# ── Row helpers ──────────────────────────────────────────────────────────────


class TestRowWithActivation:
    def test_row_with_activation(self):
        row = {
            "name": "test", "content": "content", "system": 0,
            "created_at": "now", "updated_at": "now",
            "akt_active": 1, "akt_priority": 5, "akt_man_sync": 1,
            "akt_created_at": "now", "akt_updated_at": "now",
        }
        result = SieveService._row_with_activation(row)
        assert result["name"] == "test"
        assert result["aktivado"]["active"] is True
        assert result["aktivado"]["priority"] == 5

    def test_row_without_activation(self):
        row = {
            "name": "test", "content": "content", "system": 0,
            "created_at": "now", "updated_at": "now",
            "akt_active": None, "akt_priority": None, "akt_man_sync": None,
            "akt_created_at": None, "akt_updated_at": None,
        }
        result = SieveService._row_with_activation(row)
        assert result["name"] == "test"
        assert result["aktivado"] is None
