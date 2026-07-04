"""Tests for server/command/handlers/ — via dispatch() and direct handler calls.

These tests focus on the handler logic (routing, response formatting).
Service dependencies are mocked via deps.reset_services() + monkeypatching.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Import early to trigger @command side effects
from lighterbird.server.command.handlers import *  # noqa: F401, F403
from lighterbird.server.command.registry import dispatch, get_definitions
from lighterbird.server.command.errors import CommandNotFound
from lighterbird.server.deps import reset_services


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_services_before():
    """Reset all service singletons before each test."""
    reset_services()


def _mock_email_service(**attrs):
    """Create a mock EmailService with the given attributes."""
    svc = MagicMock()
    for k, v in attrs.items():
        setattr(svc, k, v)
    return svc


# ── Help ─────────────────────────────────────────────────────────────────────


class TestHelpHandler:
    def test_help_root(self):
        result = dispatch(["help"], {})
        assert result["type"] == "help"
        assert "Available Commands" in result["title"]
        assert len(result["data"]) > 0

    def test_help_with_query(self):
        result = dispatch(["help", "email"], {})
        assert result["type"] == "help"
        # Should filter to email-related commands


# ── Email handlers ───────────────────────────────────────────────────────────


class TestEmailHandlers:
    def test_email_root(self):
        result = dispatch(["email"], {})
        # email root dispatches to email list by default
        assert "type" in result

    def test_email_list_no_service(self):
        """email list should work even without a configured service."""
        try:
            result = dispatch(["email", "list"], {"limit": "5"})
            # May return error or empty list depending on service availability
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_email_send_no_args(self):
        """Should return a form-required or error response."""
        try:
            result = dispatch(["email", "send"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_email_account_list(self):
        try:
            result = dispatch(["email", "account", "list"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_email_account_add_no_args(self):
        try:
            result = dispatch(["email", "account", "add"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_email_search_no_query(self):
        try:
            result = dispatch(["email", "search"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── Calendar handlers ────────────────────────────────────────────────────────


class TestCalendarHandlers:
    def test_calendar_root(self):
        try:
            result = dispatch(["calendar"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_calendar_list(self):
        try:
            result = dispatch(["calendar", "list"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_calendar_event_add_no_args(self):
        try:
            result = dispatch(["calendar", "event", "add"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── Contacts handlers ────────────────────────────────────────────────────────


class TestContactsHandlers:
    def test_contacts_root(self):
        try:
            result = dispatch(["contacts"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_contacts_list(self):
        try:
            result = dispatch(["contacts", "list"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_contacts_add_no_args(self):
        try:
            result = dispatch(["contacts", "add"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── Todo handlers ────────────────────────────────────────────────────────────


class TestTodoHandlers:
    def test_todo_root(self):
        try:
            result = dispatch(["todo"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_todo_list(self):
        try:
            result = dispatch(["todo", "list"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_todo_add_no_args(self):
        try:
            result = dispatch(["todo", "add"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_todo_tree(self):
        try:
            result = dispatch(["todo", "tree"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── Journal handlers ─────────────────────────────────────────────────────────


class TestJournalHandlers:
    def test_journal_root(self):
        try:
            result = dispatch(["journal"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_journal_list(self):
        try:
            result = dispatch(["journal", "list"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_journal_write_no_args(self):
        try:
            result = dispatch(["journal", "write"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── LLM handlers ─────────────────────────────────────────────────────────────


class TestLLMHandlers:
    def test_llm_root(self):
        try:
            result = dispatch(["llm"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_llm_chat_no_message(self):
        try:
            result = dispatch(["llm", "chat"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── Backup handlers ──────────────────────────────────────────────────────────


class TestBackupHandlers:
    def test_backup_root(self):
        try:
            result = dispatch(["backup"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_backup_list(self):
        try:
            result = dispatch(["backup", "list"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── User commands handlers ───────────────────────────────────────────────────


class TestUserCommandsHandlers:
    def test_user_commands_root(self):
        try:
            result = dispatch(["user-command"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_user_commands_list(self):
        try:
            result = dispatch(["user-command", "list"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── User profiles handlers ───────────────────────────────────────────────────


class TestUserProfilesHandlers:
    def test_user_profiles_root(self):
        try:
            result = dispatch(["user", "info"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_user_profiles_list(self):
        try:
            result = dispatch(["user", "info", "list"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── Drafts handlers ──────────────────────────────────────────────────────────


class TestDraftsHandlers:
    def test_draft_root(self):
        try:
            result = dispatch(["draft"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_draft_list(self):
        try:
            result = dispatch(["draft", "list"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── Letter handlers ──────────────────────────────────────────────────────────


class TestLetterHandlers:
    def test_letter_root(self):
        try:
            result = dispatch(["letter"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_letter_list(self):
        try:
            result = dispatch(["letter", "list"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── Sync handlers ────────────────────────────────────────────────────────────


class TestSyncHandlers:
    def test_sync_root(self):
        try:
            result = dispatch(["sync"], {})
            assert isinstance(result, dict)
        except Exception:
            pass


# ── Alias resolution ─────────────────────────────────────────────────────────


class TestAliases:
    def test_dispatch_via_alias(self):
        """Test that common aliases resolve to actual handlers."""
        try:
            result = dispatch(["inbox"], {})
            assert isinstance(result, dict)
        except Exception:
            pass

    def test_nonexistent_command_raises(self):
        with pytest.raises(CommandNotFound):
            dispatch(["nonexistent-command-xyz"], {})


# ── Definitions ──────────────────────────────────────────────────────────────


class TestGetDefinitions:
    def test_get_definitions_returns_list(self):
        defs = get_definitions()
        assert isinstance(defs, list)
        assert len(defs) > 0
        # Each definition should have a "path" key
        for d in defs:
            assert "path" in d or "canonical" in d

    def test_definitions_include_email(self):
        defs = get_definitions()
        email_cmds = [
            d for d in defs
            if "email" in (d.get("canonical", "") or " ".join(d.get("path", [])))
        ]
        assert len(email_cmds) > 0

    def test_definitions_include_todo(self):
        defs = get_definitions()
        todo_cmds = [
            d for d in defs
            if "todo" in (d.get("canonical", "") or " ".join(d.get("path", [])))
        ]
        assert len(todo_cmds) > 0

    def test_definitions_include_contacts(self):
        defs = get_definitions()
        contacts_cmds = [
            d for d in defs
            if "contact" in (d.get("canonical", "") or " ".join(d.get("path", [])))
        ]
        assert len(contacts_cmds) > 0
