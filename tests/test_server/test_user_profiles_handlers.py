"""Tests for user_profiles command handlers — profile CRUD and flag parsing helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lighterbird.server.command.errors import CommandValidationError

# Import early to trigger @command side effects
from lighterbird.server.command.handlers import *  # noqa: F403
from lighterbird.server.command.registry import dispatch
from lighterbird.server.command.handlers.user_profiles import (
    _extract_profile_data,
    _parse_custom_fields,
    _parse_tagged_values,
    _resolve_uuid,
)


# ── Helper tests ──────────────────────────────────────────────────────────────


class TestParseTaggedValues:
    def test_single_tag_value(self):
        """Tag:value pair returns one entry."""
        result = _parse_tagged_values("work:a@b.com")
        assert result == [{"tag": "work", "value": "a@b.com"}]

    def test_comma_separated(self):
        """Comma-separated tag:value pairs return multiple entries."""
        result = _parse_tagged_values("work:a@b.com,home:c@d.com")
        assert result == [
            {"tag": "work", "value": "a@b.com"},
            {"tag": "home", "value": "c@d.com"},
        ]

    def test_no_colon(self):
        """Value without colon gets empty tag."""
        result = _parse_tagged_values("a@b.com")
        assert result == [{"tag": "", "value": "a@b.com"}]

    def test_empty_string(self):
        """Empty string returns empty list."""
        assert _parse_tagged_values("") == []

    def test_whitespace_handling(self):
        """Surrounding whitespace is stripped."""
        result = _parse_tagged_values(" work : a@b.com , home : c@d.com ")
        assert result == [
            {"tag": "work", "value": "a@b.com"},
            {"tag": "home", "value": "c@d.com"},
        ]


class TestParseCustomFields:
    def test_single_key_value(self):
        """key:value pair returns one entry."""
        result = _parse_custom_fields("key1:val1")
        assert result == {"key1": "val1"}

    def test_multiple_pairs(self):
        """Comma-separated key:value pairs return multiple entries."""
        result = _parse_custom_fields("k1:v1,k2:v2")
        assert result == {"k1": "v1", "k2": "v2"}

    def test_no_colon(self):
        """Key without colon gets empty value."""
        result = _parse_custom_fields("key1")
        assert result == {"key1": ""}

    def test_empty_string(self):
        """Empty string returns empty dict."""
        assert _parse_custom_fields("") == {}

    def test_whitespace_handling(self):
        """Surrounding whitespace is stripped from keys and values."""
        result = _parse_custom_fields(" k1 : v1 , k2 : v2 ")
        assert result == {"k1": "v1", "k2": "v2"}


class TestExtractProfileData:
    def test_optional_name(self):
        """optional_name sets profile_name."""
        result = _extract_profile_data({}, optional_name="My Profile")
        assert result["profile_name"] == "My Profile"

    def test_standard_flags(self):
        """Standard --first-name, --last-name etc map to data keys."""
        result = _extract_profile_data(
            {
                "first-name": "Alice",
                "last-name": "Smith",
                "organization": "ACME",
                "address": "123 Main St",
            },
            optional_name="work",
        )
        assert result["profile_name"] == "work"
        assert result["given_name"] == "Alice"
        assert result["family_name"] == "Smith"
        assert result["organization"] == "ACME"
        assert result["address"] == "123 Main St"

    def test_email_flag(self):
        """--email flag is parsed via _parse_tagged_values and JSON-serialized."""
        result = _extract_profile_data({"email": "work:a@b.com"})
        assert "emails" in result
        import json
        parsed = json.loads(result["emails"])
        assert parsed == [{"tag": "work", "value": "a@b.com"}]

    def test_phone_flag(self):
        """--phone flag is JSON-serialized."""
        result = _extract_profile_data({"phone": "mobile:+1234567890"})
        import json
        parsed = json.loads(result["phones"])
        assert parsed == [{"tag": "mobile", "value": "+1234567890"}]

    def test_custom_fields_flag(self):
        """--custom flag is JSON-serialized."""
        result = _extract_profile_data({"custom": "k1:v1,k2:v2"})
        import json
        parsed = json.loads(result["custom_fields"])
        assert parsed == {"k1": "v1", "k2": "v2"}

    def test_existing_data_merges(self):
        """existing parameter is used as base for updates."""
        existing = {"profile_name": "old", "organization": "Old Corp"}
        result = _extract_profile_data({"first-name": "Bob"}, existing=existing)
        # existing is only used for its structure reference, not merged
        assert "profile_name" not in result
        assert result["given_name"] == "Bob"

    def test_empty_flags(self):
        """Empty flags dict returns empty dict."""
        assert _extract_profile_data({}) == {}


class TestResolveUuid:
    def test_uuid_prefix_match(self):
        """UUID-like string matching an existing profile returns full UUID."""
        svc = MagicMock()
        svc.list.return_value = [
            {"uuid": "abc12345-def0-1234-5678-123456789abc", "profile_name": "work"},
            {"uuid": "def67890-aaaa-bbbb-cccc-123456789abc", "profile_name": "personal"},
        ]
        result = _resolve_uuid(svc, "abc12345")
        assert result == "abc12345-def0-1234-5678-123456789abc"

    def test_name_match(self):
        """Profile name match returns UUID."""
        svc = MagicMock()
        svc.list.return_value = [
            {"uuid": "abc-123", "profile_name": "work"},
            {"uuid": "def-456", "profile_name": "Personal"},
        ]
        result = _resolve_uuid(svc, "personal")
        assert result == "def-456"

    def test_name_case_insensitive(self):
        """Profile name matching is case-insensitive."""
        svc = MagicMock()
        svc.list.return_value = [
            {"uuid": "abc-123", "profile_name": "Work Profile"},
        ]
        result = _resolve_uuid(svc, "work profile")
        assert result == "abc-123"

    def test_not_found(self):
        """Returns None when no match."""
        svc = MagicMock()
        svc.list.return_value = []
        result = _resolve_uuid(svc, "nonexistent")
        assert result is None

    def test_short_input_not_uuid_like(self):
        """Strings shorter than 6 hex chars fall through to name lookup."""
        svc = MagicMock()
        svc.list.return_value = [{"uuid": "abc-123", "profile_name": "xy"}]
        # "xy" has only 2 chars → not uuid-like → name lookup
        result = _resolve_uuid(svc, "xy")
        assert result == "abc-123"


# ── Handler tests ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_profiles_svc(monkeypatch):
    """Inject a mock profile service into deps."""
    from lighterbird.server import deps

    svc = MagicMock()
    deps._services["profiles"] = svc
    return svc


class TestUserProfilesRoot:
    def test_user_info_root(self, mock_profiles_svc):
        """!user info returns status with command list."""
        result = dispatch(["user", "info"], {})
        assert result["type"] == "status"
        assert result["title"] == "User Profiles"

    def test_user_root_overrides(self, mock_profiles_svc):
        """!user shows both saved-commands and info in summary."""
        result = dispatch(["user"], {})
        assert result["type"] == "status"
        assert result["title"] == "User Commands"
        assert "saved-commands" in result["data"]["_summary"]
        assert "info" in result["data"]["_summary"]


class TestUserProfilesList:
    def test_user_info_list(self, mock_profiles_svc):
        """!user info list returns profiles."""
        mock_profiles_svc.list.return_value = [
            {
                "uuid": "abc12345-def0-1234-5678-123456789abc",
                "profile_name": "work",
                "full_name": "Alice Smith",
                "_primary_email": "alice@work.com",
                "organization": "ACME",
                "updated_at": "2024-01-01",
            },
        ]
        result = dispatch(["user", "info", "list"], {})
        assert result["type"] == "status"
        assert result["title"] == "User Profiles"
        assert result["data"]["total"] == 1
        assert result["data"]["user_profiles"][0]["profile_name"] == "work"
        assert result["data"]["user_profiles"][0]["uuid"] == "abc12345"

    def test_user_info_list_empty(self, mock_profiles_svc):
        """Empty list returns zero total."""
        mock_profiles_svc.list.return_value = []
        result = dispatch(["user", "info", "list"], {})
        assert result["data"]["total"] == 0


class TestUserProfilesAdd:
    def test_user_info_add_missing_name(self, mock_profiles_svc):
        """Missing profile name raises."""
        with pytest.raises(CommandValidationError, match="Missing profile name"):
            dispatch(["user", "info", "add"], {})

    def test_user_info_add_success(self, mock_profiles_svc):
        """Creates a profile and returns status."""
        mock_profiles_svc.create.return_value = {
            "uuid": "abc12345-def0-1234-5678-123456789abc",
            "profile_name": "work",
            "full_name": "Alice Smith",
        }
        result = dispatch(
            ["user", "info", "add", "work"],
            {"first-name": "Alice", "last-name": "Smith"},
        )
        assert result["type"] == "status"
        assert result["title"] == "Profile Created"
        assert result["data"]["uuid"] == "abc12345"
        assert result["data"]["profile_name"] == "work"

    def test_user_info_add_profile_error(self, mock_profiles_svc):
        """ProfileError is re-raised as CommandValidationError."""
        mock_profiles_svc.create.side_effect = (
            __import__("lighterbird.profiles.services.profiles", fromlist=["ProfileError"])
            .ProfileError("Name already exists")
        )
        with pytest.raises(CommandValidationError, match="Name already exists"):
            dispatch(["user", "info", "add", "work"], {})

    def test_user_info_add_unexpected_error(self, mock_profiles_svc):
        """Generic Exception is wrapped in CommandValidationError."""
        mock_profiles_svc.create.side_effect = RuntimeError("DB connection lost")
        with pytest.raises(CommandValidationError, match="Failed to create profile"):
            dispatch(["user", "info", "add", "work"], {})


class TestUserProfilesView:
    def test_user_info_view_missing_uuid(self, mock_profiles_svc):
        """Missing UUID raises."""
        with pytest.raises(CommandValidationError, match="Missing profile UUID"):
            dispatch(["user", "info", "view"], {})

    def test_user_info_view_not_found(self, mock_profiles_svc):
        """Non-existent UUID raises."""
        mock_profiles_svc.get.return_value = None
        with pytest.raises(CommandValidationError, match="Profile not found"):
            dispatch(["user", "info", "view", "abc12345"], {})

    def test_user_info_view_success(self, mock_profiles_svc):
        """Returns profile details with JSON fields parsed."""
        mock_profiles_svc.get.return_value = {
            "uuid": "abc12345-def0-1234-5678-123456789abc",
            "profile_name": "work",
            "full_name": "Alice Smith",
            "emails": '[{"tag":"work","value":"a@b.com"}]',
            "phones": "[]",
            "custom_fields": "{}",
        }
        result = dispatch(["user", "info", "view", "abc12345"], {})
        assert result["type"] == "status"
        assert result["title"] == "Profile: work"
        # JSON fields should be parsed into Python objects
        assert result["data"]["emails"] == [{"tag": "work", "value": "a@b.com"}]
        assert result["data"]["phones"] == []


class TestUserProfilesModify:
    def test_user_info_modify_missing_uuid(self, mock_profiles_svc):
        """Missing UUID raises."""
        with pytest.raises(CommandValidationError, match="Missing profile UUID"):
            dispatch(["user", "info", "modify"], {})

    def test_user_info_modify_not_found(self, mock_profiles_svc):
        """Non-existent UUID raises."""
        mock_profiles_svc.get.return_value = None
        with pytest.raises(CommandValidationError, match="Profile not found"):
            dispatch(["user", "info", "modify", "abc12345"], {})

    def test_user_info_modify_no_fields(self, mock_profiles_svc):
        """No update flags raises."""
        mock_profiles_svc.get.return_value = {
            "uuid": "abc-123", "profile_name": "work",
        }
        with pytest.raises(CommandValidationError, match="No fields to update"):
            dispatch(["user", "info", "modify", "abc12345"], {})

    def test_user_info_modify_success(self, mock_profiles_svc):
        """Updates profile and returns status."""
        mock_profiles_svc.get.return_value = {
            "uuid": "abc12345-def0-...",
            "profile_name": "work",
            "full_name": "Alice Smith",
        }
        mock_profiles_svc.update.return_value = {
            "uuid": "abc12345-def0-...",
            "profile_name": "work",
            "full_name": "Alice B. Smith",
        }
        result = dispatch(
            ["user", "info", "modify", "abc12345"],
            {"first-name": "Alice B."},
        )
        assert result["type"] == "status"
        assert result["title"] == "Profile Updated"
        assert result["data"]["uuid"] == "abc12345"

    def test_user_info_modify_profile_error(self, mock_profiles_svc):
        """ProfileError from service is re-raised."""
        mock_profiles_svc.get.return_value = {
            "uuid": "abc-123", "profile_name": "work",
        }
        mock_profiles_svc.update.side_effect = (
            __import__("lighterbird.profiles.services.profiles", fromlist=["ProfileError"])
            .ProfileError("Update conflict")
        )
        with pytest.raises(CommandValidationError, match="Update conflict"):
            dispatch(
                ["user", "info", "modify", "abc12345"],
                {"first-name": "Alice B."},
            )


class TestUserProfilesDelete:
    def test_user_info_delete_missing_uuid(self, mock_profiles_svc):
        """Missing UUID raises."""
        with pytest.raises(
            CommandValidationError, match="Missing profile UUID or name"
        ):
            dispatch(["user", "info", "delete"], {})

    def test_user_info_delete_success(self, mock_profiles_svc):
        """Deletes profiles and returns removed/not_found lists."""
        mock_profiles_svc.list.return_value = [
            {"uuid": "abc12345-def0-...", "profile_name": "work"},
        ]
        mock_profiles_svc.delete.return_value = True
        result = dispatch(
            ["user", "info", "delete", "abc12345", "nonexistent"],
            {},
        )
        assert result["type"] == "status"
        assert result["title"] == "Profile(s) Deleted"
        assert "abc12345" in result["data"]["removed"][0]
        assert len(result["data"]["not_found"]) == 1

    def test_user_info_delete_by_name(self, mock_profiles_svc):
        """Deletes by profile name (not just UUID)."""
        mock_profiles_svc.list.return_value = [
            {"uuid": "abc12345-...", "profile_name": "work"},
        ]
        mock_profiles_svc.delete.return_value = True
        result = dispatch(["user", "info", "delete", "work"], {})
        assert len(result["data"]["removed"]) == 1
        mock_profiles_svc.delete.assert_called_once_with("abc12345-...")
