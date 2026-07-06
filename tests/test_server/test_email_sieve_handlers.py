"""Tests for email_sieve command handlers — sieve script CRUD and activation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lighterbird.server.command.errors import CommandValidationError

# Import early to trigger @command side effects
from lighterbird.server.command.handlers import *  # noqa: F403
from lighterbird.server.command.registry import dispatch


@pytest.fixture
def mock_sieve_svc(monkeypatch):
    """Inject a mock email service with .sieve sub-mock into deps."""
    from lighterbird.server import deps

    svc = MagicMock()
    svc.sieve = MagicMock()
    # _resolve_account_identifier uses get_account + db.execute
    svc.get_account = MagicMock(return_value=None)
    svc._db = MagicMock()
    svc._db.execute.return_value = []
    deps._services["email"] = svc
    return svc


class TestEmailSieveRoot:
    def test_sieve_root(self, mock_sieve_svc):
        """!email sieve returns status with command list."""
        result = dispatch(["email", "sieve"], {})
        assert result["type"] == "status"
        assert result["title"] == "Sieve Commands"
        assert "!email sieve list" in result["data"]["_summary"]


class TestEmailSieveList:
    def test_sieve_list_no_account(self, mock_sieve_svc):
        """!email sieve list returns all scripts when no --account given."""
        mock_sieve_svc.sieve.list_scripts.return_value = [
            {"name": "filter1", "content": "..."},
            {"name": "vacation", "content": "..."},
        ]
        result = dispatch(["email", "sieve", "list"], {})
        assert result["type"] == "status"
        assert result["title"] == "Sieve Scripts"
        assert len(result["data"]["scripts"]) == 2
        mock_sieve_svc.sieve.list_scripts.assert_called_once_with(account_email=None)

    def test_sieve_list_with_account(self, mock_sieve_svc):
        """!email sieve list --account email filters by account."""
        mock_sieve_svc.get_account.return_value = {"email": "me@example.com"}
        mock_sieve_svc.sieve.list_scripts.return_value = [{"name": "filter1"}]
        result = dispatch(
            ["email", "sieve", "list"], {"account": "me@example.com"}
        )
        assert result["title"] == "Sieve Scripts"
        mock_sieve_svc.sieve.list_scripts.assert_called_once()
        args = mock_sieve_svc.sieve.list_scripts.call_args
        assert args[1]["account_email"] == "me@example.com"

    def test_sieve_list_account_resolved_via_prefix(self, mock_sieve_svc):
        """Account prefix resolved via db.execute when get_account misses."""
        mock_sieve_svc.get_account.return_value = None
        mock_sieve_svc.db.execute.return_value = [
            {"email": "me@example.com"},
        ]
        mock_sieve_svc.sieve.list_scripts.return_value = []
        result = dispatch(
            ["email", "sieve", "list"], {"account": "me"}
        )
        assert result["type"] == "status"
        mock_sieve_svc.sieve.list_scripts.assert_called_once_with(
            account_email="me@example.com"
        )


class TestEmailSieveView:
    def test_sieve_view_missing_name(self, mock_sieve_svc):
        """Missing script name raises CommandValidationError."""
        with pytest.raises(CommandValidationError, match="Missing script name"):
            dispatch(["email", "sieve", "view"], {})

    def test_sieve_view_with_account(self, mock_sieve_svc):
        """With --account, uses get_script_with_activation."""
        mock_sieve_svc.get_account.return_value = {"email": "me@example.com"}
        mock_sieve_svc.sieve.get_script_with_activation.return_value = {
            "name": "filter1", "content": "sieve text",
        }
        result = dispatch(
            ["email", "sieve", "view", "filter1"], {"account": "me@example.com"}
        )
        assert result["title"] == "Sieve: filter1"
        mock_sieve_svc.sieve.get_script_with_activation.assert_called_once_with(
            "filter1", account_email="me@example.com"
        )

    def test_sieve_view_without_account(self, mock_sieve_svc):
        """Without --account, uses get_script."""
        mock_sieve_svc.sieve.get_script.return_value = {
            "name": "filter1", "content": "sieve text",
        }
        result = dispatch(["email", "sieve", "view", "filter1"], {})
        assert result["title"] == "Sieve: filter1"
        mock_sieve_svc.sieve.get_script.assert_called_once_with("filter1")

    def test_sieve_view_not_found(self, mock_sieve_svc):
        """Non-existent script raises CommandValidationError."""
        mock_sieve_svc.sieve.get_script.return_value = None
        with pytest.raises(CommandValidationError, match="Script not found"):
            dispatch(["email", "sieve", "view", "nonexistent"], {})


class TestEmailSieveAdd:
    def test_sieve_add_missing_name(self, mock_sieve_svc):
        """Missing script name raises CommandValidationError."""
        with pytest.raises(CommandValidationError, match="Missing script name"):
            dispatch(["email", "sieve", "add"], {})

    def test_sieve_add_with_content(self, mock_sieve_svc):
        """With --content flag, creates the script."""
        mock_sieve_svc.sieve.create_script.return_value = {
            "name": "myfilter", "content": "require ...",
        }
        result = dispatch(
            ["email", "sieve", "add", "myfilter"],
            {"content": "require [\"fileinto\"];"},
        )
        assert result["type"] == "status"
        assert result["title"] == "Script Created"
        assert result["data"]["name"] == "myfilter"
        mock_sieve_svc.sieve.create_script.assert_called_once_with(
            name="myfilter", content='require ["fileinto"];'
        )

    def test_sieve_add_with_file(self, mock_sieve_svc, tmp_path):
        """With --file flag, reads file content and creates the script."""
        script_file = tmp_path / "myscript.sieve"
        script_file.write_text("require [\"fileinto\"];", encoding="utf-8")
        mock_sieve_svc.sieve.create_script.return_value = {
            "name": "myscript", "content": script_file.read_text(),
        }
        result = dispatch(
            ["email", "sieve", "add", "myscript"],
            {"file": str(script_file)},
        )
        assert result["type"] == "status"
        mock_sieve_svc.sieve.create_script.assert_called_once()

    def test_sieve_add_file_not_found(self, mock_sieve_svc):
        """Non-existent --file path raises CommandValidationError."""
        with pytest.raises(CommandValidationError, match="File not found"):
            dispatch(
                ["email", "sieve", "add", "myscript"],
                {"file": "/nonexistent/path.sieve"},
            )

    def test_sieve_add_no_content_opens_form(self, mock_sieve_svc):
        """Without --content or --file, returns form-type response."""
        result = dispatch(["email", "sieve", "add", "myscript"], {})
        assert result["type"] == "form"
        assert result["title"] == "New Sieve Script"
        assert result["data"]["submit"] == "email.sieve.add"
        assert any(f["name"] == "content" for f in result["data"]["fields"])

    def test_sieve_add_value_error(self, mock_sieve_svc):
        """Service ValueError is re-raised as CommandValidationError."""
        mock_sieve_svc.sieve.create_script.side_effect = ValueError(
            "Script name already exists"
        )
        with pytest.raises(CommandValidationError, match="Script name already exists"):
            dispatch(
                ["email", "sieve", "add", "myfilter"],
                {"content": "require ..."},
            )


class TestEmailSieveModify:
    def test_sieve_modify_missing_name(self, mock_sieve_svc):
        """Missing script name raises CommandValidationError."""
        with pytest.raises(CommandValidationError, match="Missing script name"):
            dispatch(["email", "sieve", "modify"], {})

    def test_sieve_modify_with_content(self, mock_sieve_svc):
        """With --content flag, updates the script."""
        mock_sieve_svc.sieve.update_script.return_value = {
            "name": "filter1", "content": "updated",
        }
        result = dispatch(
            ["email", "sieve", "modify", "filter1"],
            {"content": "new content"},
        )
        assert result["type"] == "status"
        assert result["title"] == "Script Updated"
        mock_sieve_svc.sieve.update_script.assert_called_once_with(
            "filter1", new_name=None, content="new content"
        )

    def test_sieve_modify_with_new_name(self, mock_sieve_svc):
        """With --new-name flag, renames the script."""
        mock_sieve_svc.sieve.update_script.return_value = {
            "name": "newname", "content": "...",
        }
        result = dispatch(
            ["email", "sieve", "modify", "filter1"],
            {"new-name": "newname"},
        )
        assert result["title"] == "Script Updated"
        mock_sieve_svc.sieve.update_script.assert_called_once_with(
            "filter1", new_name="newname", content=None
        )

    def test_sieve_modify_not_found(self, mock_sieve_svc):
        """When update_script returns None, raises."""
        mock_sieve_svc.sieve.update_script.return_value = None
        with pytest.raises(CommandValidationError, match="Script not found"):
            dispatch(
                ["email", "sieve", "modify", "nonexistent"],
                {"content": "new"},
            )

    def test_sieve_modify_value_error(self, mock_sieve_svc):
        """Service ValueError is re-raised as CommandValidationError."""
        mock_sieve_svc.sieve.update_script.side_effect = ValueError(
            "Invalid script"
        )
        with pytest.raises(CommandValidationError, match="Invalid script"):
            dispatch(
                ["email", "sieve", "modify", "filter1"],
                {"content": "bad"},
            )


class TestEmailSieveDelete:
    def test_sieve_delete_missing_name(self, mock_sieve_svc):
        """Missing script name raises CommandValidationError."""
        with pytest.raises(CommandValidationError, match="Missing script name"):
            dispatch(["email", "sieve", "delete"], {})

    def test_sieve_delete_not_found(self, mock_sieve_svc):
        """When delete_script returns falsy, raises."""
        mock_sieve_svc.sieve.delete_script.return_value = None
        with pytest.raises(CommandValidationError, match="Script not found"):
            dispatch(["email", "sieve", "delete", "nonexistent"], {})

    def test_sieve_delete_success(self, mock_sieve_svc):
        """Successful delete returns status with script name."""
        mock_sieve_svc.sieve.delete_script.return_value = True
        result = dispatch(["email", "sieve", "delete", "oldscript"], {})
        assert result["type"] == "status"
        assert result["title"] == "Script Deleted"
        assert result["data"]["name"] == "oldscript"


class TestEmailSieveActivate:
    def test_sieve_activate_missing_name(self, mock_sieve_svc):
        """Missing script name raises."""
        with pytest.raises(CommandValidationError, match="Missing script name"):
            dispatch(["email", "sieve", "activate"], {"account": "me@x.com"})

    def test_sieve_activate_missing_account(self, mock_sieve_svc):
        """Missing --account flag raises."""
        with pytest.raises(CommandValidationError, match="Missing --account"):
            dispatch(["email", "sieve", "activate", "filter1"], {})

    def test_sieve_activate_unresolvable_account(self, mock_sieve_svc):
        """Unresolvable account raises."""
        mock_sieve_svc.get_account.return_value = None
        mock_sieve_svc.db.execute.return_value = []
        with pytest.raises(CommandValidationError, match="Account not found"):
            dispatch(
                ["email", "sieve", "activate", "filter1"],
                {"account": "unknown"},
            )

    def test_sieve_activate_not_found(self, mock_sieve_svc):
        """When activate_script returns None, raises."""
        mock_sieve_svc.get_account.return_value = {"email": "me@x.com"}
        mock_sieve_svc.sieve.activate_script.return_value = None
        with pytest.raises(CommandValidationError, match="Script not found"):
            dispatch(
                ["email", "sieve", "activate", "filter1"],
                {"account": "me@x.com"},
            )

    def test_sieve_activate_success(self, mock_sieve_svc):
        """Successful activate returns status with name and account."""
        mock_sieve_svc.get_account.return_value = {"email": "me@x.com"}
        mock_sieve_svc.sieve.activate_script.return_value = {
            "name": "filter1", "active": True,
        }
        result = dispatch(
            ["email", "sieve", "activate", "filter1"],
            {"account": "me@x.com", "priority": "10"},
        )
        assert result["type"] == "status"
        assert result["title"] == "Script Activated"
        assert result["data"]["name"] == "filter1"
        assert result["data"]["account"] == "me@x.com"
        mock_sieve_svc.sieve.activate_script.assert_called_once_with(
            "filter1", account_email="me@x.com", priority=10
        )


class TestEmailSieveDeactivate:
    def test_sieve_deactivate_missing_name(self, mock_sieve_svc):
        """Missing script name raises."""
        with pytest.raises(CommandValidationError, match="Missing script name"):
            dispatch(["email", "sieve", "deactivate"], {"account": "me@x.com"})

    def test_sieve_deactivate_missing_account(self, mock_sieve_svc):
        """Missing --account flag raises."""
        with pytest.raises(CommandValidationError, match="Missing --account"):
            dispatch(["email", "sieve", "deactivate", "filter1"], {})

    def test_sieve_deactivate_not_found(self, mock_sieve_svc):
        """When deactivate_script returns None, raises."""
        mock_sieve_svc.get_account.return_value = {"email": "me@x.com"}
        mock_sieve_svc.sieve.deactivate_script.return_value = None
        with pytest.raises(CommandValidationError, match="Script not found"):
            dispatch(
                ["email", "sieve", "deactivate", "filter1"],
                {"account": "me@x.com"},
            )

    def test_sieve_deactivate_success(self, mock_sieve_svc):
        """Successful deactivate returns status."""
        mock_sieve_svc.get_account.return_value = {"email": "me@x.com"}
        mock_sieve_svc.sieve.deactivate_script.return_value = {
            "name": "filter1", "active": False,
        }
        result = dispatch(
            ["email", "sieve", "deactivate", "filter1"],
            {"account": "me@x.com"},
        )
        assert result["type"] == "status"
        assert result["title"] == "Script Deactivated"


class TestEmailSievePriority:
    def test_sieve_priority_missing_args(self, mock_sieve_svc):
        """Missing name or priority raises."""
        with pytest.raises(CommandValidationError, match="Missing script name or priority"):
            dispatch(["email", "sieve", "priority", "filter1"], {})
        with pytest.raises(CommandValidationError, match="Missing script name or priority"):
            dispatch(["email", "sieve", "priority"], {})

    def test_sieve_priority_invalid_priority(self, mock_sieve_svc):
        """Non-numeric priority raises."""
        with pytest.raises(CommandValidationError, match="Invalid priority"):
            dispatch(
                ["email", "sieve", "priority", "filter1", "abc"],
                {"account": "me@x.com"},
            )

    def test_sieve_priority_missing_account(self, mock_sieve_svc):
        """Missing --account flag raises."""
        with pytest.raises(CommandValidationError, match="Missing --account"):
            dispatch(["email", "sieve", "priority", "filter1", "5"], {})

    def test_sieve_priority_not_activated(self, mock_sieve_svc):
        """When set_priority returns None, raises with activation hint."""
        mock_sieve_svc.get_account.return_value = {"email": "me@x.com"}
        mock_sieve_svc.sieve.set_priority.return_value = None
        with pytest.raises(
            CommandValidationError, match="not activated"
        ):
            dispatch(
                ["email", "sieve", "priority", "filter1", "5"],
                {"account": "me@x.com"},
            )

    def test_sieve_priority_success(self, mock_sieve_svc):
        """Successful priority set returns status."""
        mock_sieve_svc.get_account.return_value = {"email": "me@x.com"}
        mock_sieve_svc.sieve.set_priority.return_value = {"name": "filter1"}
        result = dispatch(
            ["email", "sieve", "priority", "filter1", "10"],
            {"account": "me@x.com"},
        )
        assert result["type"] == "status"
        assert result["title"] == "Priority Set"
        assert result["data"]["priority"] == 10
        assert result["data"]["name"] == "filter1"
        mock_sieve_svc.sieve.set_priority.assert_called_once_with(
            "filter1", account_email="me@x.com", priority=10
        )
