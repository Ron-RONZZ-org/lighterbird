"""Tests for server/command/handlers/ — via dispatch().

Service dependencies are mocked so tests verify handler logic
(routing, response formatting, error handling) without touching
real services or databases.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lighterbird.server.command.errors import CommandNotFound, CommandValidationError

# Import early to trigger @command side effects
from lighterbird.server.command.handlers import *  # noqa: F403
from lighterbird.server.command.registry import dispatch, get_definitions

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _mock_svc(**attrs) -> MagicMock:
    """Create a mock service with the given attributes (all MagicMocks)."""
    svc = MagicMock()
    for k, v in attrs.items():
        if callable(v):
            setattr(svc, k, v)
        else:
            setattr(svc, k, MagicMock(return_value=v))
    return svc


@pytest.fixture
def mock_email_svc(monkeypatch):
    """Inject a mock into the deps._services registry."""
    from lighterbird.server import deps
    svc = _mock_svc(
        list_accounts=[],
        search_messages=[],
        list_messages=[],
        get_message=None,
        trash_message=None,
        export_eml=None,
        import_eml=None,
        send_email={"status": "sent"},
    )
    deps._services["email"] = svc
    return svc


@pytest.fixture
def mock_calendar_svc(monkeypatch):
    """Inject a mock into the deps._services registry."""
    from lighterbird.server import deps
    svc = _mock_svc(
        list_calendars=[],
        list_events=[],
        get_event=None,
    )
    deps._services["calendar"] = svc
    return svc


@pytest.fixture
def mock_contact_svc(monkeypatch):
    """Inject a mock into the deps._services registry."""
    from lighterbird.server import deps
    svc = _mock_svc(
        list_contacts=[],
        search_contacts=[],
        get_contact=None,
    )
    deps._services["contact"] = svc
    return svc


@pytest.fixture
def mock_todo_svc(monkeypatch):
    """Inject a mock into the deps._services registry."""
    from lighterbird.server import deps
    svc = _mock_svc(
        list_todos=[],
        search_todos=[],
        get_todo=None,
    )
    deps._services["todo"] = svc
    return svc


@pytest.fixture
def mock_journal_svc(monkeypatch):
    """Inject a mock into the deps._services registry."""
    from lighterbird.server import deps
    svc = _mock_svc(
        list_entries=[],
        search_entries=[],
        get_entry=None,
    )
    deps._services["journal"] = svc
    return svc


@pytest.fixture
def mock_letter_svc(monkeypatch):
    """Inject a mock into the deps._services registry."""
    from lighterbird.server import deps
    svc = _mock_svc(
        list_letters=[],
        search_letters=[],
        get_letter=None,
    )
    deps._services["letter"] = svc
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


# ── Email handlers ───────────────────────────────────────────────────────────


class TestEmailHandlers:
    def test_email_root(self, mock_email_svc):
        """email root redirects to list due to default_action."""
        result = dispatch(["email"], {})
        assert result["type"] == "email-list"
        assert "data" in result

    def test_email_list(self, mock_email_svc):
        """email list returns messages from the mocked service."""
        mock_email_svc.search_messages.return_value = [
            {"uuid": "abc123", "subject": "Test", "from_addr": "a@b.com"},
        ]
        result = dispatch(["email", "list"], {"limit": "5"})
        assert result["type"] == "email-list"
        assert result["data"]["total"] == 1
        assert result["data"]["messages"][0]["subject"] == "Test"

    def test_email_list_empty(self, mock_email_svc):
        """email list works with no messages."""
        result = dispatch(["email", "list"], {"limit": "5"})
        assert result["type"] == "email-list"
        assert result["data"]["total"] == 0

    def test_email_send_missing_args(self):
        """email send with too few args raises CommandValidationError."""
        with pytest.raises(CommandValidationError, match="Missing required args"):
            dispatch(["email", "send"], {})

    def test_email_send_no_account(self, mock_email_svc):
        """email send raises if no accounts configured."""
        with pytest.raises(CommandValidationError, match="No email accounts configured"):
            dispatch(["email", "send", "to@b.com", "Subject", "Body"], {})

    def test_email_send_success(self, mock_email_svc):
        """email send with valid args sends and returns status."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        result = dispatch(["email", "send", "to@b.com", "Subject", "Body"], {})
        assert result["type"] == "status"
        assert result["title"] == "Sent"

    def test_email_read_missing_uuid(self):
        """email read without uuid raises."""
        with pytest.raises(CommandValidationError, match="Missing message UUID"):
            dispatch(["email", "read"], {})

    def test_email_read_not_found(self, mock_email_svc):
        """email read with non-existent uuid raises."""
        with pytest.raises(CommandValidationError, match="Message not found"):
            dispatch(["email", "read", "nonexistent-uuid"], {})

    def test_email_read_success(self, mock_email_svc):
        """email read returns an email response."""
        mock_email_svc.get_message.return_value = {
            "uuid": "abc123",
            "subject": "Hello",
            "from_addr": "a@b.com",
        }
        result = dispatch(["email", "read", "abc123"], {})
        assert result["type"] == "email"
        assert result["title"] == "Hello"

    def test_email_trash_missing_uuid(self):
        """email trash without uuid raises."""
        with pytest.raises(CommandValidationError, match="Missing message UUID"):
            dispatch(["email", "trash"], {})

    def test_email_trash_success(self, mock_email_svc):
        """email trash calls trash_message and returns status."""
        result = dispatch(["email", "trash", "abc123"], {})
        assert result["type"] == "status"
        assert result["title"] == "Trashed"
        mock_email_svc.trash_message.assert_called_once_with("abc123")

    def test_email_archive_success(self, mock_email_svc):
        """email archive calls move_message to Archive folder and returns status."""
        result = dispatch(["email", "archive", "abc123"], {})
        assert result["type"] == "status"
        assert result["title"] == "Archived"
        mock_email_svc.move_message.assert_called_once_with("abc123", "Archive")

    def test_email_search_no_filters(self, mock_email_svc):
        """email search without filters calls list_messages."""
        mock_email_svc.list_messages.return_value = [
            {"uuid": "abc", "subject": "Test"},
        ]
        result = dispatch(["email", "search"], {})
        assert result["type"] == "email-list"
        assert result["title"] == "Search Results"
        assert result["data"]["total"] == 1

    def test_email_search_with_query(self, mock_email_svc):
        """email search with query passes it to search_messages."""
        mock_email_svc.search_messages.return_value = [
            {"uuid": "abc", "subject": "Hello world"},
        ]
        result = dispatch(["email", "search", "hello world"], {})
        assert result["type"] == "email-list"
        mock_email_svc.search_messages.assert_called_once()
        filters = mock_email_svc.search_messages.call_args[0][0]
        assert filters.get("query") == "hello world"

    def test_email_export_eml_missing_uuid(self):
        """email export eml without uuid raises."""
        with pytest.raises(CommandValidationError, match="Missing message UUID"):
            dispatch(["email", "export", "eml"], {})

    def test_email_export_eml_success(self, mock_email_svc):
        """email export eml returns status with eml_size."""
        mock_email_svc.export_eml.return_value = "From: test\r\nSubject: Test\r\n\r\nBody"
        result = dispatch(["email", "export", "eml", "abc123"], {})
        assert result["type"] == "status"
        assert result["title"] == "Export .eml"
        assert result["data"]["eml_size"] > 0

    def test_email_export_eml_not_found(self, mock_email_svc):
        """email export eml for non-existent message raises."""
        with pytest.raises(CommandValidationError, match="Message not found"):
            dispatch(["email", "export", "eml", "abc123"], {})

    def test_email_import_eml_missing_path(self):
        """email import eml without path raises."""
        with pytest.raises(CommandValidationError, match="Missing file path"):
            dispatch(["email", "import", "eml"], {})

    def test_email_import_eml_success(self, mock_email_svc, tmp_path):
        """email import eml returns status with draft info."""
        eml_file = tmp_path / "test.eml"
        eml_file.write_text("From: test@x.com\nSubject: Test\n")
        mock_email_svc.import_eml.return_value = {
            "uuid": "draft-123",
            "data": {"subject": "Imported"},
        }
        result = dispatch(["email", "import", "eml", str(eml_file)], {})
        assert result["type"] == "status"
        assert result["title"] == "Import .eml"
        assert result["data"]["draft_uuid"] == "draft-123"

    def test_email_import_eml_file_not_found(self, mock_email_svc):
        """email import eml with non-existent file raises."""
        with pytest.raises(CommandValidationError, match="File not found"):
            dispatch(["email", "import", "eml", "/nonexistent/test.eml"], {})

    def test_email_import_eml_generic_error(self, mock_email_svc, tmp_path):
        """email import eml with unexpected error raises."""
        eml_file = tmp_path / "bad.eml"
        eml_file.write_text("From: test@x.com\nSubject: Bad\n")
        mock_email_svc.import_eml.side_effect = ValueError("Corrupted file")
        with pytest.raises(CommandValidationError, match="Import failed"):
            dispatch(["email", "import", "eml", str(eml_file)], {})

    def test_email_reply_missing_uuid(self):
        """email reply without uuid raises."""
        with pytest.raises(CommandValidationError, match="Missing message UUID"):
            dispatch(["email", "reply"], {})

    def test_email_reply_not_found(self, mock_email_svc):
        """email reply with non-existent uuid raises."""
        with pytest.raises(CommandValidationError, match="Message not found"):
            dispatch(["email", "reply", "abc123"], {})

    def test_email_reply_success(self, mock_email_svc):
        """email reply opens compose form pre-populated."""
        mock_email_svc.get_message.return_value = {
            "uuid": "abc123",
            "subject": "Original",
            "from_addr": "sender@b.com",
            "to_recipients": ["me@b.com"],
            "body": "Hello!",
            "account_email": "me@b.com",
        }
        result = dispatch(["email", "reply", "abc123"], {})
        assert result["type"] == "form-required"
        assert result["title"] == "Reply"
        assert result["data"]["form"] == "email-send"
        assert "Re: Original" in result["data"]["initialData"]["subject"]
        assert "sender@b.com" in result["data"]["initialData"]["to"]

    def test_email_forward_missing_uuid(self):
        """email forward without uuid raises."""
        with pytest.raises(CommandValidationError, match="Missing message UUID"):
            dispatch(["email", "forward"], {})

    def test_email_forward_not_found(self, mock_email_svc):
        """email forward with non-existent uuid raises."""
        with pytest.raises(CommandValidationError, match="Message not found"):
            dispatch(["email", "forward", "abc123"], {})

    def test_email_forward_success(self, mock_email_svc):
        """email forward opens compose form pre-populated."""
        mock_email_svc.get_message.return_value = {
            "uuid": "abc123",
            "subject": "Original",
            "from_addr": "sender@b.com",
            "body": "Hello!",
            "account_email": "me@b.com",
        }
        result = dispatch(["email", "forward", "abc123"], {})
        assert result["type"] == "form-required"
        assert result["title"] == "Forward"
        assert result["data"]["form"] == "email-send"
        assert "Fwd: Original" in result["data"]["initialData"]["subject"]

# ── Calendar handlers ────────────────────────────────────────────────────────


class TestCalendarHandlers:
    def test_calendar_root(self, mock_calendar_svc):
        result = dispatch(["calendar"], {})
        assert isinstance(result, dict)
        assert "type" in result

    def test_calendar_list(self, mock_calendar_svc):
        result = dispatch(["calendar", "list"], {})
        assert isinstance(result, dict)

    def test_calendar_event_add_no_args(self, mock_calendar_svc):
        """event add with no calendars raises."""
        with pytest.raises(CommandValidationError, match="No calendars configured"):
            dispatch(["calendar", "event", "add"], {})


# ── Contacts handlers ────────────────────────────────────────────────────────


class TestContactsHandlers:
    def test_contacts_root(self, mock_contact_svc):
        """contacts root uses 'contact' command path (alias 'contacts' resolves to it)."""
        result = dispatch(["contact"], {})
        assert isinstance(result, dict)
        assert "type" in result

    def test_contacts_list(self, mock_contact_svc):
        result = dispatch(["contact", "list"], {})
        assert isinstance(result, dict)

    def test_contacts_add_no_args(self, mock_contact_svc):
        """contact add without flags raises CommandValidationError."""
        with pytest.raises(CommandValidationError, match="Missing contact name"):
            dispatch(["contact", "add"], {})


# ── Todo handlers ────────────────────────────────────────────────────────────


class TestTodoHandlers:
    def test_todo_root(self, mock_todo_svc):
        result = dispatch(["todo"], {})
        assert isinstance(result, dict)
        assert "type" in result

    def test_todo_list(self, mock_todo_svc):
        result = dispatch(["todo", "list"], {})
        assert isinstance(result, dict)

    def test_todo_add_no_args(self, mock_todo_svc):
        """todo add without title raises."""
        with pytest.raises(CommandValidationError, match="Missing todo title"):
            dispatch(["todo", "add"], {})

    def test_todo_tree(self, mock_todo_svc):
        result = dispatch(["todo", "tree"], {})
        assert isinstance(result, dict)


# ── Journal handlers ─────────────────────────────────────────────────────────


class TestJournalHandlers:
    def test_journal_root(self, mock_journal_svc):
        result = dispatch(["journal"], {})
        assert isinstance(result, dict)
        assert "type" in result

    def test_journal_list(self, mock_journal_svc):
        result = dispatch(["journal", "list"], {})
        assert isinstance(result, dict)

    def test_journal_write_no_args(self, mock_journal_svc):
        """journal write without title raises."""
        with pytest.raises(CommandValidationError, match="Missing journal entry title"):
            dispatch(["journal", "write"], {})


# ── LLM handlers ─────────────────────────────────────────────────────────────


class TestLLMHandlers:
    def test_llm_root(self):
        result = dispatch(["llm"], {})
        assert isinstance(result, dict)
        assert "type" in result

    def test_llm_chat_no_message(self):
        """llm chat with no profile raises CommandValidationError (no profile named chat)."""
        with pytest.raises(CommandValidationError, match="Profile not found"):
            dispatch(["llm", "chat"], {})


# ── Backup handlers ──────────────────────────────────────────────────────────


class TestBackupHandlers:
    def test_backup_root(self):
        result = dispatch(["backup"], {})
        assert isinstance(result, dict)
        assert "type" in result

    def test_backup_list(self):
        result = dispatch(["backup", "list"], {})
        assert isinstance(result, dict)


# ── User commands handlers ───────────────────────────────────────────────────


class TestUserCommandsHandlers:
    def test_user_saved_commands_root(self):
        """user.saved-commands is the correct command path."""
        result = dispatch(["user", "saved-commands"], {})
        assert isinstance(result, dict)
        assert "type" in result
        assert "Saved Commands" in result["title"]

    def test_user_saved_commands_list(self):
        result = dispatch(["user", "saved-commands", "list"], {})
        assert isinstance(result, dict)
        assert "saved-commands" in result["type"]


# ── User profiles handlers ───────────────────────────────────────────────────


class TestUserProfilesHandlers:
    def test_user_profiles_root(self):
        result = dispatch(["user", "info"], {})
        assert isinstance(result, dict)
        assert "type" in result

    def test_user_profiles_list(self):
        result = dispatch(["user", "info", "list"], {})
        assert isinstance(result, dict)


# ── Drafts handlers ──────────────────────────────────────────────────────────


class TestDraftsHandlers:
    def test_email_draft_list(self):
        """email draft (no args) lists drafts."""
        result = dispatch(["email", "draft"], {})
        assert isinstance(result, dict)
        assert "type" in result

    def test_email_draft_not_found(self):
        """email draft <uuid> with non-existent draft raises."""
        with pytest.raises(CommandValidationError, match="Draft not found"):
            dispatch(["email", "draft", "nonexistent-uuid"], {})


# ── Letter handlers ──────────────────────────────────────────────────────────


class TestLetterHandlers:
    def test_letter_root(self, mock_letter_svc):
        result = dispatch(["letter"], {})
        assert isinstance(result, dict)
        assert "type" in result

    def test_letter_list(self, mock_letter_svc):
        result = dispatch(["letter", "list"], {})
        assert isinstance(result, dict)


# ── Sync handlers ────────────────────────────────────────────────────────────


class TestSyncHandlers:
    def test_sync_root(self):
        result = dispatch(["sync"], {})
        assert isinstance(result, dict)
        assert "type" in result


# ── Alias resolution ─────────────────────────────────────────────────────────


class TestAliases:
    def test_nonexistent_command_raises(self):
        with pytest.raises(CommandNotFound):
            dispatch(["nonexistent-command-xyz"], {})


# ── Definitions ──────────────────────────────────────────────────────────────


class TestGetDefinitions:
    def test_get_definitions_returns_list(self):
        defs = get_definitions()
        assert isinstance(defs, list)
        assert len(defs) > 0
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
        contact_cmds = [
            d for d in defs
            if "contact" in (d.get("canonical", "") or " ".join(d.get("path", [])))
        ]
        assert len(contact_cmds) > 0
