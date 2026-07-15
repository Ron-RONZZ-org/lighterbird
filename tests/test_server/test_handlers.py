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
        create_event=None,
        delete_event=None,
        import_ics=None,
        export_ics=None,
    )
    svc.calendars = MagicMock()
    svc.events = MagicMock()
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
        create=None,
        update=None,
        delete=None,
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
        create=None,
        update=None,
        delete=None,
        mark_done=None,
        get_with_children=None,
        flatten_tree=None,
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
        create=None,
        delete=None,
        export_md=None,
        import_md=None,
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
        create=None,
        export_md=None,
        import_md=None,
    )
    svc.normalize_tags = MagicMock(return_value=[])
    svc.set_tags = MagicMock()
    svc.convert_to_html = MagicMock(return_value="<p>body</p>")
    svc.store_body = MagicMock()
    deps._services["letter"] = svc
    return svc


@pytest.fixture
def mock_tag_svc(monkeypatch):
    """Inject a mock tag service."""
    from lighterbird.server import deps
    svc = _mock_svc(
        list_tags=[],
        list_tags_for_domain=[],
        create_tag=None,
        rename_tag=None,
        delete_tag=None,
    )
    deps._services["tag"] = svc
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
        """email send with valid args queues for background delivery."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        result = dispatch(["email", "send", "to@b.com", "Subject", "Body"], {})
        assert result["type"] == "status"
        # Always queued — SMTP delivery happens asynchronously via outbox
        assert result["title"] == "Queued for Delivery"
        assert result["data"]["folder"] == "Outbox"

    def test_email_send_passes_signature_format(self, mock_email_svc):
        """email send passes signature_format parameter to svc.send_email()."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        dispatch(["email", "send", "to@b.com", "Subject", "Body"], {})
        call_kwargs = mock_email_svc.send_email.call_args[1]
        assert call_kwargs.get("signature_format") == "plain"

    def test_email_send_passes_signature_format_explicit(self, mock_email_svc):
        """email send passes explicit signature-format flag."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        dispatch(
            ["email", "send", "to@b.com", "Subject", "Body"],
            {"signature": "Best,\nMe", "signature-format": "html"},
        )
        call_kwargs = mock_email_svc.send_email.call_args[1]
        assert call_kwargs.get("signature_format") == "html"

    def test_email_send_value_error(self, mock_email_svc):
        """email send converts ValueError from svc to CommandValidationError."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        mock_email_svc.send_email.side_effect = ValueError("No password configured")
        with pytest.raises(CommandValidationError, match="No password configured"):
            dispatch(["email", "send", "to@b.com", "Subject", "Body"], {})

    def test_email_send_attachment_json(self, mock_email_svc):
        """email send accepts JSON-encoded file attachments."""
        import json
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        attachments = json.dumps([
            {"name": "report.pdf", "data": "dGVzdA=="},
            {"name": "photo.jpg", "data": "cGhvdG8="},
        ])
        dispatch(
            ["email", "send", "to@b.com", "Subject", "Body"],
            {"file": attachments},
        )
        call_kwargs = mock_email_svc.send_email.call_args[1]
        atts = call_kwargs.get("attachments")
        assert atts == [
            {"name": "report.pdf", "data": "dGVzdA=="},
            {"name": "photo.jpg", "data": "cGhvdG8="},
        ]

    def test_email_send_attachment_with_special_chars(self, mock_email_svc):
        """email send handles filenames with colons and commas via JSON."""
        import json
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        attachments = json.dumps([
            {"name": "report:2024.pdf", "data": "dGVzdA=="},
            {"name": "notes, final.txt", "data": "bm90ZXM="},
        ])
        dispatch(
            ["email", "send", "to@b.com", "Subject", "Body"],
            {"file": attachments},
        )
        call_kwargs = mock_email_svc.send_email.call_args[1]
        atts = call_kwargs.get("attachments")
        # Names with colons/commas are preserved intact with JSON encoding
        assert atts[0]["name"] == "report:2024.pdf"
        assert atts[1]["name"] == "notes, final.txt"

    def test_email_send_attachment_legacy_fallback(self, mock_email_svc):
        """email send falls back to legacy CSV format for backward compat."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        dispatch(
            ["email", "send", "to@b.com", "Subject", "Body"],
            {"file": "readme.txt:dGV4dA==,archive.zip:emlw"},
        )
        call_kwargs = mock_email_svc.send_email.call_args[1]
        atts = call_kwargs.get("attachments")
        assert atts == [
            {"name": "readme.txt", "data": "dGV4dA=="},
            {"name": "archive.zip", "data": "emlw"},
        ]

    def test_email_send_in_reply_to(self, mock_email_svc):
        """email send passes in-reply-to flag."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        dispatch(
            ["email", "send", "to@b.com", "Subject", "Body"],
            {"in-reply-to": "<msg123@example.com>"},
        )
        call_kwargs = mock_email_svc.send_email.call_args[1]
        assert call_kwargs.get("in_reply_to") == "<msg123@example.com>"

    def test_email_send_no_signature(self, mock_email_svc):
        """email send passes signature='' when --no-signature is set."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        dispatch(
            ["email", "send", "to@b.com", "Subject", "Body"],
            {"no-signature": "true"},
        )
        call_kwargs = mock_email_svc.send_email.call_args[1]
        # --no-signature should set signature to empty string
        assert call_kwargs.get("signature") == ""

    def test_email_send_signature_name(self, mock_email_svc):
        """email send resolves named signature via svc.signatures.resolve()."""
        mock_sigs = MagicMock()
        mock_sigs.resolve.return_value = {
            "signature_text": "Best,\nJohn",
            "signature_format": "html",
        }
        mock_email_svc.signatures = mock_sigs
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        dispatch(
            ["email", "send", "to@b.com", "Subject", "Body"],
            {"signature-name": "sig1"},
        )
        mock_sigs.resolve.assert_called_once()
        call_kwargs = mock_email_svc.send_email.call_args[1]
        assert call_kwargs.get("signature") == "Best,\nJohn"
        assert call_kwargs.get("signature_format") == "html"

    def test_email_send_attachment_empty_json_array(self, mock_email_svc):
        """email send accepts empty JSON array [] as --file."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        dispatch(
            ["email", "send", "to@b.com", "Subject", "Body"],
            {"file": "[]"},
        )
        call_kwargs = mock_email_svc.send_email.call_args[1]
        assert call_kwargs.get("attachments") == []

    def test_email_send_attachment_json_non_list(self, mock_email_svc):
        """Valid JSON that is not a list leaves attachments=None (no fallback)."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        # JSON object (not list) does NOT match isinstance(parsed, list)
        # and does NOT raise JSONDecodeError, so attachments stays None
        dispatch(
            ["email", "send", "to@b.com", "Subject", "Body"],
            {"file": '{"name":"test","data":"dGVzdA=="}'},
        )
        call_kwargs = mock_email_svc.send_email.call_args[1]
        assert call_kwargs.get("attachments") is None

    def test_email_send_attachment_malformed_json(self, mock_email_svc):
        """Malformed --file value falls back to legacy CSV format."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        dispatch(
            ["email", "send", "to@b.com", "Subject", "Body"],
            {"file": "readme.txt:dGV4dA==,archive.zip:emlw"},
        )
        call_kwargs = mock_email_svc.send_email.call_args[1]
        atts = call_kwargs.get("attachments")
        assert atts == [
            {"name": "readme.txt", "data": "dGV4dA=="},
            {"name": "archive.zip", "data": "emlw"},
        ]

    def test_email_send_invalid_body_format(self, mock_email_svc):
        """email send with invalid body-format raises CommandValidationError."""
        mock_email_svc.list_accounts.return_value = [{"email": "me@b.com"}]
        with pytest.raises(CommandValidationError, match="Invalid body-format"):
            dispatch(
                ["email", "send", "to@b.com", "Subject", "Body"],
                {"body-format": "docx"},
            )

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

    def test_email_delete_missing_uuid(self):
        """email delete without uuid raises."""
        with pytest.raises(CommandValidationError, match="Missing message UUID"):
            dispatch(["email", "delete"], {})

    def test_email_delete_success(self, mock_email_svc):
        """email delete calls trash_message and returns status."""
        result = dispatch(["email", "delete", "abc123"], {})
        assert result["type"] == "status"
        assert result["title"] == "Trashed"
        mock_email_svc.trash_message.assert_called_once_with("abc123")

    def test_email_delete_hard_success(self, mock_email_svc):
        """email delete --hard calls hard_delete_message and returns status."""
        result = dispatch(["email", "delete", "abc123"], {"hard": ""})
        assert result["type"] == "status"
        assert result["title"] == "Permanently Deleted"
        mock_email_svc.msg_ops.hard_delete_message.assert_called_once_with("abc123")

    def test_email_trash_list_opens_trash_view(self):
        """email trash list returns email-list with isTrashView and Trash filter."""
        result = dispatch(["email", "trash", "list"], {})
        assert result["type"] == "email-list"
        assert result.get("idKey") == "email-trash-list"
        assert result["data"].get("_isTrashView") is True
        assert result["data"].get("filters", {}).get("folder") == "Trash"

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

    def test_email_list_body_preview_truncated(self, mock_email_svc):
        """email list truncates body to 2000 chars with [...] note."""
        mock_email_svc.search_messages.return_value = [
            {"uuid": "abc123", "subject": "Long", "from_addr": "a@b.com",
             "body": "A" * 5000, "html_body": "<p>html</p>"},
        ]
        result = dispatch(["email", "list"], {})
        msgs = result["data"]["messages"]
        assert len(msgs) == 1
        assert len(msgs[0]["body"]) <= 2010  # 2000 + "[...]"
        assert msgs[0]["body"].endswith("[...]")
        assert msgs[0]["html_body"] == ""

    def test_email_list_body_short_not_truncated(self, mock_email_svc):
        """email list keeps short body unchanged."""
        mock_email_svc.search_messages.return_value = [
            {"uuid": "abc123", "subject": "Short", "from_addr": "a@b.com",
             "body": "Hello!", "html_body": ""},
        ]
        result = dispatch(["email", "list"], {})
        msgs = result["data"]["messages"]
        assert msgs[0]["body"] == "Hello!"

    def test_email_reply_truncates_long_body(self, mock_email_svc):
        """email reply truncates body to 100 lines / 10K chars."""
        long_body = "\n".join(f"Line {i}" for i in range(200))
        mock_email_svc.get_message.return_value = {
            "uuid": "abc123", "subject": "Original", "from_addr": "a@b.com",
            "to_recipients": ["me@b.com"], "body": long_body, "account_email": "me@b.com",
        }
        result = dispatch(["email", "reply", "abc123"], {})
        quoted = result["data"]["initialData"]["body"]
        # Should have at most 103 lines (blank + 100 quoted + [...] note)
        assert quoted.count("\n") <= 103, f"Too many lines: {quoted.count('\n')}"
        assert "100 more lines" in quoted, "Expected truncation note in reply"

    def test_email_forward_truncates_long_body(self, mock_email_svc):
        """email forward truncates body to 100 lines / 10K chars."""
        long_body = "\n".join(f"Line {i}" for i in range(200))
        mock_email_svc.get_message.return_value = {
            "uuid": "abc123", "subject": "Original", "from_addr": "a@b.com",
            "body": long_body, "account_email": "me@b.com",
        }
        result = dispatch(["email", "forward", "abc123"], {})
        body = result["data"]["initialData"]["body"]
        assert "100 more lines" in body, "Expected truncation note in forward"

    def test_email_forward_with_attachments(self, mock_email_svc, monkeypatch):
        """email forward includes attachments from the original message."""
        import base64
        from unittest.mock import MagicMock

        mock_store = MagicMock()
        mock_store.retrieve.return_value = b"fake_pdf_content"
        monkeypatch.setattr("lighterbird.server.command.handlers.email.AttachmentStore", lambda: mock_store)

        mock_db = MagicMock()
        mock_db.execute.return_value = [
            {"filename": "doc.pdf", "content_id": "cid1"},
        ]
        mock_email_svc.db = mock_db
        mock_email_svc.get_message.return_value = {
            "uuid": "abc123", "subject": "Original", "from_addr": "a@b.com",
            "body": "Hello!", "account_email": "me@b.com",
        }

        result = dispatch(["email", "forward", "abc123"], {})
        files = result["data"]["initialData"].get("files", [])
        assert len(files) == 1
        assert files[0]["name"] == "doc.pdf"
        assert files[0]["data"] == base64.b64encode(b"fake_pdf_content").decode("ascii")

# ── Email folder handlers ─────────────────────────────────────────────────────


class TestEmailFolderHandlers:
    """!email folder {list,add,rename,move,delete} handlers."""

    def test_email_folder_root(self, mock_email_svc):
        """email folder root shows available subcommands."""
        result = dispatch(["email", "folder"], {})
        assert result["type"] == "status"
        assert "folder" in result["title"].lower()
        assert "_summary" in result["data"]

    def test_email_folder_list(self, mock_email_svc):
        """email folder list returns folder-list type with tree data."""
        mock_email_svc.db.execute.return_value = [
            {"account_email": "a@b.com", "name": "INBOX",
             "special_use": "\\Inbox", "created_at": "", "updated_at": ""},
            {"account_email": "a@b.com", "name": "Sent",
             "special_use": "\\Sent", "created_at": "", "updated_at": ""},
        ]
        result = dispatch(["email", "folder", "list"], {})
        assert result["type"] == "folder-list"
        assert result["title"] == "Folders"
        assert len(result["data"]["folders"]) == 2
        assert result["data"]["folders"][0]["folder_name"] == "INBOX"
        assert result["data"]["folders"][0]["account_email"] == "a@b.com"
        assert "accounts" in result["data"]

    def test_email_folder_list_empty(self, mock_email_svc):
        """email folder list works with no folders."""
        mock_email_svc.db.execute.return_value = []
        result = dispatch(["email", "folder", "list"], {})
        assert result["type"] == "folder-list"
        assert result["data"]["total"] == 0

    def test_email_folder_add_missing_name(self, mock_email_svc):
        """email folder add without name raises error."""
        from lighterbird.server.command.errors import CommandValidationError
        with pytest.raises(CommandValidationError, match="Missing folder name"):
            dispatch(["email", "folder", "add"], {})

    def test_email_folder_add_missing_parent(self, mock_email_svc):
        """email folder add with name but no --parent raises error."""
        from lighterbird.server.command.errors import CommandValidationError
        with pytest.raises(CommandValidationError, match="Missing --parent"):
            dispatch(["email", "folder", "add", "MyFolder"], {})

    def test_email_folder_rename_missing_args(self, mock_email_svc):
        """email folder rename without enough args raises error."""
        from lighterbird.server.command.errors import CommandValidationError
        with pytest.raises(CommandValidationError, match="Missing arguments"):
            dispatch(["email", "folder", "rename"], {})
        with pytest.raises(CommandValidationError, match="Missing arguments"):
            dispatch(["email", "folder", "rename", "a@b.com/INBOX"], {})

    def test_email_folder_rename_invalid_path(self, mock_email_svc):
        """email folder rename with invalid path raises error."""
        from lighterbird.server.command.errors import CommandValidationError
        with pytest.raises(CommandValidationError, match="Invalid folder path"):
            dispatch(["email", "folder", "rename", "invalid", "NewName"], {})

    def test_email_folder_move_missing_args(self, mock_email_svc):
        """email folder move without path raises error."""
        from lighterbird.server.command.errors import CommandValidationError
        with pytest.raises(CommandValidationError, match="Missing folder path"):
            dispatch(["email", "folder", "move"], {})

    def test_email_folder_move_missing_parent(self, mock_email_svc):
        """email folder move without --parent raises error."""
        from lighterbird.server.command.errors import CommandValidationError
        with pytest.raises(CommandValidationError, match="Missing --parent"):
            dispatch(["email", "folder", "move", "a@b.com/MyFolder"], {})

    def test_email_folder_delete_missing_path(self, mock_email_svc):
        """email folder delete without path raises error."""
        from lighterbird.server.command.errors import CommandValidationError
        with pytest.raises(CommandValidationError, match="Missing folder path"):
            dispatch(["email", "folder", "delete"], {})

    def test_email_folder_delete_invalid_path(self, mock_email_svc):
        """email folder delete with invalid path raises error."""
        from lighterbird.server.command.errors import CommandValidationError
        with pytest.raises(CommandValidationError, match="Invalid folder path"):
            dispatch(["email", "folder", "delete", "justaname"], {})

    def test_email_folders_alias(self, mock_email_svc):
        """!email folders (plural) alias resolves to !email folder list."""
        mock_email_svc.db.execute.return_value = [
            {"account_email": "a@b.com", "name": "INBOX",
             "special_use": "\\Inbox", "created_at": "", "updated_at": ""},
        ]
        result = dispatch(["email", "folders"], {})
        assert result["type"] == "folder-list"
        assert len(result["data"]["folders"]) == 1


# ── Email account handlers ────────────────────────────────────────────────────


class TestEmailAccountHandlers:
    def test_account_list(self, mock_email_svc):
        """email account list returns accounts."""
        mock_email_svc.list_accounts.return_value = [
            {"email": "a@b.com", "imap_server": "imap.b.com"},
        ]
        result = dispatch(["email", "account", "list"], {})
        assert result["type"] == "status"
        assert result["title"] == "Email Accounts"
        assert len(result["data"]["accounts"]) == 1

    def test_account_add_missing_email(self):
        """email account add without email raises."""
        with pytest.raises(CommandValidationError, match="Missing email"):
            dispatch(["email", "account", "add"], {})

    def test_account_add_success(self, mock_email_svc, monkeypatch):
        """email account add with valid email creates account."""
        from lighterbird.server import deps
        # Mock detect_servers to return known values
        import lighterbird.email.server_detect as sd
        monkeypatch.setattr(sd, "detect_servers", lambda email, **kw: {
            "imap": "imap.migadu.com", "smtp": "smtp.migadu.com",
            "managesieve_host": "imap.migadu.com", "managesieve_port": 4190,
            "method": "mx_provider",
        })
        mock_email_svc.create_account.return_value = {"email": "test@ronzz.org"}
        result = dispatch(["email", "account", "add", "test@ronzz.org"],
                          {"password": "secret", "name": "Test"})
        assert result["type"] == "status"
        assert result["title"] == "Account Added"
        assert result["data"]["email"] == "test@ronzz.org"

    def test_account_add_dns_fallback(self, mock_email_svc, monkeypatch):
        """email account add with unresolvable fallback returns form-required."""
        import socket
        def bad_dns(host, port):
            raise socket.gaierror("No address")
        monkeypatch.setattr(socket, "getaddrinfo", bad_dns)
        import lighterbird.email.server_detect as sd
        monkeypatch.setattr(sd, "detect_servers", lambda email, **kw: {
            "imap": "imap.unknown.domain", "smtp": "smtp.unknown.domain",
            "method": "fallback",
        })
        mock_email_svc.create_account.return_value = {"email": "x@y.com"}
        result = dispatch(["email", "account", "add", "x@y.com"], {})
        assert result["type"] == "form-required"
        assert result["data"]["form"] == "email-account-add"
        assert "does not resolve" in result["data"]["error"] or "DNS" in result["data"]["error"]

    def test_account_modify_missing_email(self):
        """email account modify without email raises."""
        with pytest.raises(CommandValidationError, match="Missing account email"):
            dispatch(["email", "account", "modify"], {})

    def test_account_modify_not_found(self, mock_email_svc):
        """email account modify for non-existent account raises."""
        mock_email_svc.get_account.return_value = None
        with pytest.raises(CommandValidationError, match="Account not found"):
            dispatch(["email", "account", "modify", "x@y.com"], {})

    def test_account_modify_name(self, mock_email_svc):
        """email account modify --name updates the account name."""
        mock_email_svc.get_account.return_value = {"email": "x@y.com"}
        mock_accounts = MagicMock()
        mock_email_svc.accounts = mock_accounts
        result = dispatch(["email", "account", "modify", "x@y.com"], {"name": "NewName"})
        assert result["type"] == "status"
        assert result["title"] == "Account Modified"
        mock_accounts.update.assert_called_once()
        args = mock_accounts.update.call_args[0]
        assert args[1].get("name") == "NewName"

    def test_account_modify_redetect(self, mock_email_svc, monkeypatch):
        """email account modify --redetect re-detects IMAP/SMTP."""
        import lighterbird.email.server_detect as sd
        monkeypatch.setattr(sd, "detect_servers", lambda email, **kw: {
            "imap": "imap.migadu.com", "smtp": "smtp.migadu.com",
            "managesieve_host": "imap.migadu.com", "managesieve_port": 4190,
            "method": "mx_provider",
        })
        mock_email_svc.get_account.return_value = {"email": "test@ronzz.org"}
        mock_accounts = MagicMock()
        mock_email_svc.accounts = mock_accounts
        result = dispatch(["email", "account", "modify", "test@ronzz.org"], {"redetect": ""})
        assert result["type"] == "status"
        mock_accounts.update.assert_called_once()
        args = mock_accounts.update.call_args[0]
        assert args[1]["imap_server"] == "imap.migadu.com"
        assert args[1]["smtp_server"] == "smtp.migadu.com"

    def test_account_modify_redetect_dns_fail(self, mock_email_svc, monkeypatch):
        """email account modify --redetect raises if detected server fails DNS."""
        import socket
        def bad_dns(host, port):
            raise socket.gaierror("No address")
        monkeypatch.setattr(socket, "getaddrinfo", bad_dns)
        import lighterbird.email.server_detect as sd
        monkeypatch.setattr(sd, "detect_servers", lambda email, **kw: {
            "imap": "imap.bad.domain", "smtp": "smtp.bad.domain",
            "method": "fallback",
        })
        mock_email_svc.get_account.return_value = {"email": "x@y.com"}
        with pytest.raises(CommandValidationError, match="does not resolve"):
            dispatch(["email", "account", "modify", "x@y.com"], {"redetect": ""})

    def test_account_delete_missing_email(self):
        """email account delete without email raises."""
        with pytest.raises(CommandValidationError, match="Missing email"):
            dispatch(["email", "account", "delete"], {})

    def test_account_delete_success(self, mock_email_svc):
        """email account delete removes the account."""
        mock_email_svc.delete_account = MagicMock()
        result = dispatch(["email", "account", "delete", "x@y.com"], {})
        assert result["type"] == "status"
        assert result["title"] == "Account(s) Deleted"
        mock_email_svc.delete_account.assert_called_once_with("x@y.com")


# ── Email signature handlers ──────────────────────────────────────────────────


class TestEmailSignatureHandlers:
    def test_signature_list(self, mock_email_svc):
        """email signature list returns signatures."""
        mock_sigs = MagicMock()
        mock_sigs.list_signatures.return_value = [
            {"uuid": "sig-1", "name": "sig1", "body": "Hello"},
        ]
        mock_sigs.get_account_default_uuid.return_value = None
        mock_email_svc.signatures = mock_sigs
        result = dispatch(["email", "signature", "list"], {})
        assert result["type"] == "status"
        assert "Signatures" in result["title"]
        assert len(result["data"]["signatures"]) == 1

    def test_signature_add_missing_name(self, mock_email_svc):
        """email signature add without --name raises."""
        with pytest.raises(CommandValidationError, match="Missing"):
            dispatch(["email", "signature", "add"], {})

    def test_signature_add_success(self, mock_email_svc):
        """email signature add creates a new signature."""
        mock_sigs = MagicMock()
        mock_sigs.create.return_value = {"uuid": "sig-1", "name": "sig1"}
        mock_email_svc.signatures = mock_sigs
        result = dispatch(["email", "signature", "add", "sig1", "Best regards"],
                          {"format": "plain"})
        assert result["type"] == "status"
        mock_sigs.create.assert_called_once_with("sig1", "Best regards", signature_format="plain")

    def test_signature_modify_success(self, mock_email_svc):
        """email signature modify updates an existing signature."""
        mock_sigs = MagicMock()
        mock_sigs.get_by_name.return_value = {"uuid": "sig-1", "name": "sig1"}
        mock_sigs.update.return_value = {"uuid": "sig-1", "name": "sig1"}
        mock_email_svc.signatures = mock_sigs
        result = dispatch(["email", "signature", "modify", "sig1"],
                          {"body": "Updated"})
        assert result["type"] == "status"
        mock_sigs.update.assert_called_once()

    def test_signature_delete_success(self, mock_email_svc):
        """email signature delete removes a signature."""
        mock_sigs = MagicMock()
        mock_sigs.get_by_name.return_value = {"uuid": "sig-1", "name": "sig1"}
        mock_sigs.delete.return_value = True
        mock_email_svc.signatures = mock_sigs
        result = dispatch(["email", "signature", "delete", "sig1"], {})
        assert result["type"] == "status"
        mock_sigs.delete.assert_called_once()


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
            dispatch(["calendar", "event", "add", "Title", "2026-07-12T10:00", "2026-07-12T11:00"], {})


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

    def test_contacts_add_success(self, mock_contact_svc):
        """contact add with name creates contact."""
        mock_contact_svc.create.return_value = {"uuid": "abc123"}
        result = dispatch(["contact", "add", "Jane"],
                          {"last-name": "Doe", "email": "jane@test.com"})
        assert result["type"] == "status"
        assert result["title"] == "Contact Added"
        mock_contact_svc.create.assert_called_once()

    def test_contacts_modify_success(self, mock_contact_svc):
        """contact modify updates a contact."""
        mock_contact_svc.get.return_value = {"uuid": "abc123"}
        mock_contact_svc.update = MagicMock()
        result = dispatch(["contact", "modify", "abc123"], {"first-name": "Jane2"})
        assert result["type"] == "status"
        assert result["title"] == "Contact Modified"
        mock_contact_svc.update.assert_called_once()

    def test_contacts_delete_success(self, mock_contact_svc):
        """contact delete removes a contact."""
        mock_contact_svc.delete = MagicMock()
        result = dispatch(["contact", "delete", "abc123"], {})
        assert result["type"] == "status"
        assert "Deleted" in result["title"]
        mock_contact_svc.delete.assert_called_once_with("abc123")

    def test_contacts_search(self, mock_contact_svc):
        """contact search returns matching contacts."""
        mock_contact_svc.search.return_value = [
            {"uuid": "abc", "first_name": "Jane", "last_name": "Doe"},
        ]
        result = dispatch(["contact", "search", "Jane"], {})
        assert result["type"] == "contacts-list"
        # The backend returns messages list, the frontend parses it
        assert "data" in result


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


# ── Calendar event handlers (Phase 2) ──────────────────────────────────────────


class TestCalendarEventHandlers:
    def test_event_add_no_calendars(self, mock_calendar_svc):
        """event add with no calendars raises."""
        with pytest.raises(CommandValidationError, match="No calendars configured"):
            dispatch(["calendar", "event", "add", "Title", "2026-07-12T10:00", "2026-07-12T11:00"], {})

    def test_event_add_success(self, mock_calendar_svc):
        """event add with summary creates event."""
        mock_calendar_svc.list_calendars.return_value = [{"uuid": "cal-1"}]
        mock_calendar_svc.create_event.return_value = {"uuid": "evt-1", "title": "Test event"}
        result = dispatch(["calendar", "event", "add",
                          "Test event", "2026-07-12T10:00", "2026-07-12T11:00"], {})
        assert result["type"] == "status"
        assert result["title"] == "Event Created"
        mock_calendar_svc.create_event.assert_called_once()

    def test_event_modify_success(self, mock_calendar_svc):
        """event modify updates an event."""
        mock_calendar_svc.get_event.return_value = {"uuid": "evt-1"}
        result = dispatch(["calendar", "event", "modify", "evt-1"],
                          {"title": "Updated"})
        assert result["type"] == "status"
        assert result["title"] == "Event Modified"
        mock_calendar_svc.events.update.assert_called_once()

    def test_event_delete_success(self, mock_calendar_svc):
        """event delete removes an event."""
        mock_calendar_svc.delete_event = MagicMock()
        result = dispatch(["calendar", "event", "delete", "evt-1"], {})
        assert result["type"] == "status"
        mock_calendar_svc.delete_event.assert_called_once_with("evt-1")

    def test_event_view_success(self, mock_calendar_svc):
        """event view returns event details."""
        mock_calendar_svc.get_event.return_value = {
            "uuid": "evt-1", "title": "Meeting",
        }
        result = dispatch(["calendar", "event", "view", "evt-1"], {})
        assert result["type"] == "events"
        assert result["title"] == "Meeting"

    def test_event_search(self, mock_calendar_svc):
        """event search finds matching events."""
        mock_calendar_svc.list_events.return_value = [
            {"uuid": "evt-1", "summary": "Team sync"},
        ]
        result = dispatch(["calendar", "event", "search", "team"], {})
        assert result["type"] == "calendar-events"
        assert "data" in result

    def test_event_rrule_set(self, mock_calendar_svc):
        """event rrule set adds recurrence."""
        mock_calendar_svc.get_event.return_value = {"uuid": "evt-1"}
        result = dispatch(["calendar", "event", "rrule", "set", "evt-1", "FREQ=WEEKLY"],
                          {})
        assert result["type"] == "status"
        mock_calendar_svc.events.update.assert_called_once()

    def test_account_add_success(self, mock_calendar_svc):
        """calendar account add creates a calendar."""
        mock_calendar_svc.create_calendar.return_value = {"uuid": "cal-1"}
        result = dispatch(["calendar", "account", "add", "https://cal.example.com"],
                          {"username": "u", "password": "p"})
        assert result["type"] == "status"
        assert result["title"] == "Calendar Added"
        mock_calendar_svc.create_calendar.assert_called_once()

    def test_account_list(self, mock_calendar_svc):
        """calendar account list shows calendars."""
        mock_calendar_svc.list_calendars.return_value = [
            {"uuid": "cal-1", "url": "https://cal.example.com"},
        ]
        result = dispatch(["calendar", "account", "list"], {})
        assert result["type"] == "status"
        assert "Calendars" in result["title"]
        assert len(result["data"]["calendars"]) == 1

    def test_account_modify_success(self, mock_calendar_svc):
        """calendar account modify updates a calendar."""
        mock_calendar_svc.calendars.update = MagicMock()
        result = dispatch(["calendar", "account", "modify", "cal-1"],
                          {"url": "https://new-url.example.com"})
        assert result["type"] == "status"
        mock_calendar_svc.calendars.update.assert_called_once()

    def test_account_delete_success(self, mock_calendar_svc):
        """calendar account delete removes a calendar."""
        mock_calendar_svc.delete_calendar = MagicMock()
        result = dispatch(["calendar", "account", "delete", "cal-1"], {})
        assert result["type"] == "status"
        mock_calendar_svc.delete_calendar.assert_called_once_with("cal-1")


# ── Todo handlers (Phase 2) ──────────────────────────────────────────────────


class TestTodoHandlersPhase2:
    def test_todo_add_success(self, mock_todo_svc):
        """todo add creates a todo."""
        mock_todo_svc.create.return_value = {"uuid": "todo-1", "title": "Buy milk"}
        result = dispatch(["todo", "add", "Buy milk"], {})
        assert result["type"] == "status"
        assert result["title"] == "Todo Added"
        mock_todo_svc.create.assert_called_once()

    def test_todo_view(self, mock_todo_svc):
        """todo view returns todo details."""
        mock_todo_svc.get_with_children.return_value = {"uuid": "todo-1", "title": "Test"}
        result = dispatch(["todo", "view", "todo-1"], {})
        assert result["type"] == "status"
        assert result["title"] == "Test"

    def test_todo_done_success(self, mock_todo_svc):
        """todo done marks a todo as completed."""
        mock_todo_svc.mark_done = MagicMock()
        result = dispatch(["todo", "done", "todo-1"], {})
        assert result["type"] == "status"
        assert "Done" in result["title"]
        mock_todo_svc.mark_done.assert_called_once_with("todo-1")

    def test_todo_modify_success(self, mock_todo_svc):
        """todo modify updates a todo."""
        mock_todo_svc.update = MagicMock()
        result = dispatch(["todo", "modify", "todo-1"], {"title": "Updated"})
        assert result["type"] == "status"
        assert result["title"] == "Todo Modified"
        mock_todo_svc.update.assert_called_once()

    def test_todo_delete_success(self, mock_todo_svc):
        """todo delete removes a todo."""
        mock_todo_svc.delete = MagicMock()
        result = dispatch(["todo", "delete", "todo-1"], {})
        assert result["type"] == "status"
        assert "Deleted" in result["title"]
        mock_todo_svc.delete.assert_called_once_with("todo-1")

    def test_todo_search(self, mock_todo_svc):
        """todo search finds matching todos."""
        mock_todo_svc.search.return_value = [{"uuid": "t1", "title": "Buy milk"}]
        result = dispatch(["todo", "search", "milk"], {})
        assert result["type"] == "todo-list"
        assert "data" in result

    def test_todo_tree(self, mock_todo_svc):
        """todo tree returns tree view."""
        mock_todo_svc.list.return_value = [{"uuid": "t1", "title": "Root"}]
        mock_todo_svc.flatten_tree.return_value = [{"uuid": "t1", "title": "Root"}]
        result = dispatch(["todo", "tree"], {})
        assert result["type"] == "todo-list"

    def test_todo_export_md(self, mock_todo_svc):
        """todo export md exports todos."""
        mock_todo_svc.export_md.return_value = "# Todos\n- item"
        result = dispatch(["todo", "export", "md"], {"all": ""})
        assert result["type"] == "status"
        assert "Exported" in result["title"]

    def test_todo_import_md_missing_path(self):
        """todo import md without path raises."""
        with pytest.raises(CommandValidationError, match="Missing file path"):
            dispatch(["todo", "import", "md"], {})


# ── Journal handlers (Phase 2) ────────────────────────────────────────────────


class TestJournalHandlersPhase2:
    def test_journal_write_success(self, mock_journal_svc):
        """journal write creates an entry."""
        mock_journal_svc.create.return_value = {"uuid": "entry-1"}
        result = dispatch(["journal", "write", "My title", "My body"], {})
        assert result["type"] == "status"
        assert result["title"] == "Journal Entry Written"
        mock_journal_svc.create.assert_called_once()

    def test_journal_view(self, mock_journal_svc):
        """journal view returns entry."""
        mock_journal_svc.get.return_value = {"uuid": "entry-1", "title": "Day 1"}
        result = dispatch(["journal", "view", "entry-1"], {})
        assert result["type"] == "status"
        assert result["title"] == "Day 1"

    def test_journal_search(self, mock_journal_svc):
        """journal search finds entries."""
        mock_journal_svc.search.return_value = [{"uuid": "e1", "title": "Found"}]
        result = dispatch(["journal", "search", "query"], {})
        assert result["type"] == "journal-list"

    def test_journal_delete_success(self, mock_journal_svc):
        """journal delete removes an entry."""
        mock_journal_svc.get.return_value = {"uuid": "entry-1"}
        mock_journal_svc.delete = MagicMock()
        result = dispatch(["journal", "delete", "entry-1"], {})
        assert result["type"] == "status"
        assert "Deleted" in result["title"]
        mock_journal_svc.delete.assert_called_once()

    def test_journal_export_md(self, mock_journal_svc):
        """journal export md exports entries."""
        mock_journal_svc.export_md.return_value = "# Journal\n- entry"
        result = dispatch(["journal", "export", "md", "--all"], {})
        assert result["type"] == "markdown"

    def test_journal_import_md_missing_path(self):
        """journal import md without path raises."""
        with pytest.raises(CommandValidationError, match="Missing file path"):
            dispatch(["journal", "import", "md"], {})


# ── Letter handlers (Phase 2) ────────────────────────────────────────────────


class TestLetterHandlersPhase2:
    def test_letter_add_success(self, mock_letter_svc):
        """letter add creates a letter."""
        mock_letter_svc.create.return_value = {"uuid": "ltr-1"}
        result = dispatch(["letter", "add", "John Doe"],
                          {"direction": "received"})
        assert result["type"] == "status"
        assert result["title"] == "Letter Added"
        mock_letter_svc.create.assert_called_once()

    def test_letter_view(self, mock_letter_svc):
        """letter view returns letter details."""
        mock_letter_svc.get_with_thread.return_value = {"uuid": "ltr-1"}
        result = dispatch(["letter", "view", "ltr-1"], {})
        assert result["type"] == "letter-view"

    def test_letter_export_md(self, mock_letter_svc):
        """letter export md exports a letter."""
        mock_letter_svc.get.return_value = {"uuid": "ltr-1"}
        mock_letter_svc.export_md.return_value = "# Letter"
        result = dispatch(["letter", "export", "md", "ltr-1"], {})
        assert result["type"] == "status"
        assert "Exported" in result["title"]

    def test_letter_import_md_missing_path(self):
        """letter import md without path raises."""
        with pytest.raises(CommandValidationError, match="Missing file path"):
            dispatch(["letter", "import", "md"], {})


# ── Tags handlers (Phase 2) ────────────────────────────────────────────────────


class TestTagHandlers:
    def test_tag_root(self):
        """tag root shows help."""
        result = dispatch(["tag"], {})
        assert isinstance(result, dict)
        assert "type" in result

    def test_tag_list(self, mock_tag_svc):
        """tag list returns tags."""
        mock_tag_svc.list_tags.return_value = [
            {"name": "work", "color": "blue"},
        ]
        result = dispatch(["tag", "list"], {})
        assert result["type"] == "status"
        assert "Tags" in result["title"]
        assert len(result["data"]["tags"]) == 1

    def test_tag_create_success(self, mock_tag_svc):
        """tag create adds a tag."""
        mock_tag_svc.create_tag.return_value = {"name": "work", "color": "blue"}
        result = dispatch(["tag", "create", "work"], {"color": "blue"})
        assert result["type"] == "status"
        mock_tag_svc.create_tag.assert_called_once_with("work", color="blue")

    def test_tag_rename_success(self, mock_tag_svc):
        """tag rename renames a tag."""
        mock_tag_svc.rename_tag.return_value = {"name": "new"}
        result = dispatch(["tag", "rename", "old", "new"], {})
        assert result["type"] == "status"
        mock_tag_svc.rename_tag.assert_called_once_with("old", "new")

    def test_tag_delete_success(self, mock_tag_svc):
        """tag delete removes a tag."""
        result = dispatch(["tag", "delete", "work"], {})
        assert result["type"] == "status"
        mock_tag_svc.delete_tag.assert_called_once_with("work")


# ── Backup handlers (Phase 2) ─────────────────────────────────────────────────


class TestBackupHandlersPhase2:
    def test_backup_now(self, monkeypatch):
        """backup now triggers a new backup."""
        def fake_backup_all():
            yield {"kind": "data", "path": "/tmp/test", "size": 100}
        monkeypatch.setattr("lighterbird.server.command.handlers.backup_actions.backup_all_strategies",
                          fake_backup_all)
        monkeypatch.setattr("lighterbird.server.command.handlers.backup_actions.backup_config_files",
                          lambda: [])
        monkeypatch.setattr("lighterbird.server.command.handlers.backup_actions.load_config",
                          lambda: {"strategies": []})
        result = dispatch(["backup", "now"], {})
        assert result["type"] == "status"
        assert "Backup" in result["title"]


# ── Sync handlers (Phase 2) ───────────────────────────────────────────────────


class TestSyncHandlersPhase2:
    def test_sync_cmd(self, mock_email_svc, monkeypatch):
        """sync triggers email and calendar sync."""
        mock_email_svc.sync_all = MagicMock()
        mock_email_svc.sync_account = MagicMock()
        monkeypatch.setattr("lighterbird.server.command.handlers.sync.get_calendar_service",
                          lambda: MagicMock())
        monkeypatch.setattr("lighterbird.server.command.handlers.sync.get_todo_service",
                          lambda: MagicMock())
        result = dispatch(["sync"], {})
        assert result["type"] == "status"
        assert "Sync" in result["title"]


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
