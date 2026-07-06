"""Tests for letter_crud command handlers — letter list, add, view."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lighterbird.server.command.errors import CommandValidationError

# Import early to trigger @command side effects
from lighterbird.server.command.handlers import *  # noqa: F403
from lighterbird.server.command.registry import dispatch


@pytest.fixture
def mock_letter_svc(monkeypatch):
    """Inject a mock letter service into deps."""
    from lighterbird.server import deps

    svc = MagicMock()
    svc.list.return_value = []
    svc.list_grouped.return_value = []
    svc.get.return_value = None
    svc.get_with_thread.return_value = None
    svc.get_body.return_value = None
    svc.create.return_value = {"uuid": "let-123", "object": "Test"}
    svc.normalize_tags.return_value = []
    svc.convert_to_html.return_value = "<p>body</p>"
    deps._services["letter"] = svc
    return svc


class TestLetterRoot:
    def test_letter_root(self, mock_letter_svc):
        """!letter returns status response (default_action=list)."""
        result = dispatch(["letter"], {})
        assert isinstance(result, dict)
        assert "type" in result


class TestLetterList:
    def test_letter_list(self, mock_letter_svc):
        """!letter list returns letter-list type with letters."""
        mock_letter_svc.list.return_value = [
            {"uuid": "let-001", "object": "Hello", "sender_manual": "Alice"},
        ]
        result = dispatch(["letter", "list"], {})
        assert result["type"] == "letter-list"
        assert result["title"] == "Letters"
        assert result["data"]["total"] == 1
        assert result["data"]["letters"][0]["object"] == "Hello"

    def test_letter_list_with_direction_and_sort(self, mock_letter_svc):
        """List forwards direction and sort flags to service."""
        mock_letter_svc.list.return_value = []
        result = dispatch(
            ["letter", "list"],
            {"direction": "sent", "sort": "oldest", "limit": "10"},
        )
        assert result["type"] == "letter-list"
        mock_letter_svc.list.assert_called_once()
        args = mock_letter_svc.list.call_args[1]
        assert args["direction"] == "sent"
        assert args["desc"] is False
        assert args["limit"] == 10

    def test_letter_list_grouped(self, mock_letter_svc):
        """With --group conversation, calls list_grouped."""
        mock_letter_svc.list_grouped.return_value = [
            {"uuid": "let-001", "object": "Thread"},
        ]
        result = dispatch(["letter", "list"], {"group": "conversation"})
        assert result["data"]["total"] == 1
        mock_letter_svc.list_grouped.assert_called_once_with(limit=20)
        mock_letter_svc.list.assert_not_called()

    def test_letter_list_sort_sender(self, mock_letter_svc):
        """--sort sender maps to order_by=sender_manual, desc=False."""
        mock_letter_svc.list.return_value = []
        dispatch(["letter", "list"], {"sort": "sender"})
        args = mock_letter_svc.list.call_args[1]
        assert args["order_by"] == "sender_manual"
        assert args["desc"] is False

    def test_letter_list_with_tag(self, mock_letter_svc):
        """--tag flag is normalized and passed to list call."""
        mock_letter_svc.normalize_tags.return_value = ["important"]
        mock_letter_svc.list.return_value = []
        dispatch(["letter", "list"], {"tag": "important"})
        mock_letter_svc.normalize_tags.assert_called_once_with(["important"])
        args = mock_letter_svc.list.call_args[1]
        assert args["tags"] == ["important"]


class TestLetterAdd:
    def test_letter_add_missing_object(self, mock_letter_svc):
        """Missing object raises CommandValidationError."""
        with pytest.raises(CommandValidationError, match="Missing letter object"):
            dispatch(["letter", "add"], {})

    def test_letter_add_success(self, mock_letter_svc):
        """Creates a letter and returns status."""
        mock_letter_svc.create.return_value = {
            "uuid": "let-abc", "object": "Thank You Note",
        }
        result = dispatch(
            ["letter", "add", "Thank You Note"],
            {"sender": "Alice", "recipient": "Bob"},
        )
        assert result["type"] == "status"
        assert result["title"] == "Letter Added"
        assert result["data"]["object"] == "Thank You Note"
        # Verify data passed to create
        create_call = mock_letter_svc.create.call_args[0][0]
        assert create_call["object"] == "Thank You Note"
        assert create_call["sender_manual"] == "Alice"
        assert create_call["recipient_manual"] == "Bob"

    def test_letter_add_with_tag(self, mock_letter_svc):
        """--tag flag sets tags on created letter."""
        mock_letter_svc.create.return_value = {
            "uuid": "let-abc", "object": "Test",
        }
        mock_letter_svc.normalize_tags.return_value = ["personal", "important"]
        dispatch(
            ["letter", "add", "Test"],
            {"tag": "personal,important"},
        )
        mock_letter_svc.normalize_tags.assert_called_once_with(
            ["personal,important"]
        )
        mock_letter_svc.set_tags.assert_called_once_with(
            "let-abc", ["personal", "important"]
        )

    def test_letter_add_with_respond_to(self, mock_letter_svc):
        """--respond-to looks up parent letter and links it."""
        mock_letter_svc.get.return_value = {
            "uuid": "parent-uuid", "object": "Original",
        }
        mock_letter_svc.create.return_value = {
            "uuid": "let-abc", "object": "Reply",
        }
        dispatch(
            ["letter", "add", "Reply"],
            {"respond-to": "parent-uuid"},
        )
        mock_letter_svc.get.assert_called_once_with("parent-uuid")
        create_data = mock_letter_svc.create.call_args[0][0]
        assert create_data["respond_to_uuid"] == "parent-uuid"

    def test_letter_add_respond_to_not_found(self, mock_letter_svc):
        """Non-existent --respond-to raises."""
        mock_letter_svc.get.return_value = None
        with pytest.raises(CommandValidationError, match="Letter not found"):
            dispatch(
                ["letter", "add", "Reply"],
                {"respond-to": "nonexistent"},
            )

    def test_letter_add_with_body_text(self, mock_letter_svc):
        """--body-text is converted to HTML and stored."""
        mock_letter_svc.create.return_value = {
            "uuid": "let-abc", "object": "Note",
        }
        dispatch(
            ["letter", "add", "Note"],
            {"body-text": "Hello **world**", "body-format": "markdown"},
        )
        mock_letter_svc.convert_to_html.assert_called_once_with(
            "Hello **world**", "markdown"
        )
        mock_letter_svc.store_body.assert_called_once_with(
            "let-abc", "<p>body</p>"
        )

    def test_letter_add_with_body_file(self, mock_letter_svc, tmp_path):
        """--body file is read and stored as HTML."""
        body_file = tmp_path / "letter.md"
        body_file.write_text("# Hello", encoding="utf-8")
        mock_letter_svc.create.return_value = {
            "uuid": "let-abc", "object": "Note",
        }
        dispatch(
            ["letter", "add", "Note"],
            {"body": str(body_file)},
        )
        mock_letter_svc.convert_to_html.assert_called_once_with(
            "# Hello", "markdown"
        )
        mock_letter_svc.store_body.assert_called_once()

    def test_letter_add_body_file_not_found(self, mock_letter_svc):
        """Non-existent --body file raises."""
        mock_letter_svc.create.return_value = {
            "uuid": "let-abc", "object": "Note",
        }
        with pytest.raises(CommandValidationError, match="Body file not found"):
            dispatch(
                ["letter", "add", "Note"],
                {"body": "/nonexistent/path.md"},
            )

    def test_letter_add_body_file_read_error(self, mock_letter_svc):
        """Unreadable --body file raises."""
        mock_letter_svc.create.return_value = {
            "uuid": "let-abc", "object": "Note",
        }
        with pytest.raises(
            CommandValidationError, match="Failed to read body file"
        ):
            dispatch(
                ["letter", "add", "Note"],
                {"body": "/"},
            )


class TestLetterView:
    def test_letter_view_missing_uuid(self, mock_letter_svc):
        """Missing UUID raises."""
        with pytest.raises(CommandValidationError, match="Missing UUID"):
            dispatch(["letter", "view"], {})

    def test_letter_view_not_found(self, mock_letter_svc):
        """Non-existent UUID raises."""
        mock_letter_svc.get_with_thread.return_value = None
        with pytest.raises(CommandValidationError, match="Letter not found"):
            dispatch(["letter", "view", "nonexistent"], {})

    def test_letter_view_success(self, mock_letter_svc):
        """Returns letter-view type with letter data and body."""
        mock_letter_svc.get_with_thread.return_value = {
            "uuid": "let-abc",
            "object": "Hello Letter",
        }
        mock_letter_svc.get_body.return_value = "<p>Dear John, ...</p>"
        result = dispatch(["letter", "view", "let-abc"], {})
        assert result["type"] == "letter-view"
        assert result["title"] == "Hello Letter"
        assert result["data"]["body"] == "<p>Dear John, ...</p>"
        assert result["data"]["letter"]["uuid"] == "let-abc"
