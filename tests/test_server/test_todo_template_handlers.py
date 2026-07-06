"""Tests for todo_template command handlers — template CRUD."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lighterbird.server.command.errors import CommandValidationError

# Import early to trigger @command side effects
from lighterbird.server.command.handlers import *  # noqa: F403
from lighterbird.server.command.registry import dispatch


@pytest.fixture
def mock_todo_svc(monkeypatch):
    """Inject a mock todo service into deps."""
    from lighterbird.server import deps

    svc = MagicMock()
    svc.list_templates.return_value = []
    svc.get_template_by_name.return_value = None
    svc.create_template.return_value = {"uuid": "tpl-abc", "name": "test"}
    svc.update_template.return_value = {"uuid": "tpl-abc", "name": "test"}
    svc.template_fields_in_use.return_value = {}
    deps._services["todo"] = svc
    return svc


class TestTodoTemplateRoot:
    def test_root(self, mock_todo_svc):
        """!todo template returns status with subcommand list."""
        result = dispatch(["todo", "template"], {})
        assert result["type"] == "status"
        assert result["title"] == "Template Commands"
        assert "add" in result["data"]["_summary"]
        assert "list" in result["data"]["_summary"]


class TestTodoTemplateList:
    def test_list(self, mock_todo_svc):
        """!todo template list returns templates."""
        mock_todo_svc.list_templates.return_value = [
            {"uuid": "tpl-1", "name": "daily", "fields": []},
            {"uuid": "tpl-2", "name": "weekly", "fields": []},
        ]
        result = dispatch(["todo", "template", "list"], {})
        assert result["type"] == "templates"
        assert result["title"] == "Templates"
        assert len(result["data"]["templates"]) == 2

    def test_list_empty(self, mock_todo_svc):
        """Empty template list returns zero items."""
        result = dispatch(["todo", "template", "list"], {})
        assert result["data"]["templates"] == []


class TestTodoTemplateAdd:
    def test_add_missing_name(self, mock_todo_svc):
        """Missing name raises."""
        with pytest.raises(CommandValidationError, match="Missing template name"):
            dispatch(["todo", "template", "add"], {})

    def test_add_success(self, mock_todo_svc):
        """Creates template with name."""
        mock_todo_svc.create_template.return_value = {
            "uuid": "tpl-abc", "name": "daily",
        }
        result = dispatch(["todo", "template", "add", "daily"], {})
        assert result["type"] == "status"
        assert result["title"] == "Template Created"
        assert result["data"]["name"] == "daily"

    def test_add_with_fields(self, mock_todo_svc):
        """--text, --file, --markdown flags create fields."""
        dispatch(
            ["todo", "template", "add", "project"],
            {
                "text": "deadline assignee",
                "file": "attachment",
                "markdown": "notes",
            },
        )
        create_data = mock_todo_svc.create_template.call_args[0][0]
        field_names = [f["name"] for f in create_data["fields"]]
        assert "deadline" in field_names
        assert "assignee" in field_names
        assert "attachment" in field_names
        assert "notes" in field_names
        # Verify field types
        for f in create_data["fields"]:
            if f["name"] == "deadline":
                assert f["type"] == "text"

    def test_add_with_title_placeholder(self, mock_todo_svc):
        """--title-placeholder sets default title text."""
        dispatch(
            ["todo", "template", "add", "daily"],
            {"title-placeholder": "Daily Standup"},
        )
        create_data = mock_todo_svc.create_template.call_args[0][0]
        assert create_data["title_placeholder"] == "Daily Standup"

    def test_add_value_error(self, mock_todo_svc):
        """ValueError from create_template is re-raised as CommandValidationError."""
        mock_todo_svc.create_template.side_effect = ValueError(
            "Template name already exists"
        )
        with pytest.raises(CommandValidationError, match="Template name already exists"):
            dispatch(["todo", "template", "add", "daily"], {})

    def test_add_multi_word_name(self, mock_todo_svc):
        """Multiple remaining tokens are joined as template name."""
        dispatch(["todo", "template", "add", "My", "Template"], {})
        create_data = mock_todo_svc.create_template.call_args[0][0]
        assert create_data["name"] == "My Template"


class TestTodoTemplateView:
    def test_view_missing_name(self, mock_todo_svc):
        """Missing name raises."""
        with pytest.raises(CommandValidationError, match="Missing template name"):
            dispatch(["todo", "template", "view"], {})

    def test_view_not_found(self, mock_todo_svc):
        """Non-existent template raises."""
        with pytest.raises(CommandValidationError, match="Template not found"):
            dispatch(["todo", "template", "view", "nonexistent"], {})

    def test_view_success(self, mock_todo_svc):
        """Returns status with template data."""
        mock_todo_svc.get_template_by_name.return_value = {
            "uuid": "tpl-abc", "name": "daily",
            "fields": [{"name": "deadline", "type": "text"}],
        }
        result = dispatch(["todo", "template", "view", "daily"], {})
        assert result["type"] == "status"
        assert result["title"] == "Template: daily"
        assert result["data"]["name"] == "daily"

    def test_view_multi_word_name(self, mock_todo_svc):
        """Multi-word name is joined for lookup."""
        mock_todo_svc.get_template_by_name.return_value = {
            "uuid": "tpl-abc", "name": "my template",
        }
        dispatch(["todo", "template", "view", "my", "template"], {})
        mock_todo_svc.get_template_by_name.assert_called_once_with(
            "my template"
        )


class TestTodoTemplateModify:
    def test_modify_missing_name(self, mock_todo_svc):
        """Missing name raises."""
        with pytest.raises(CommandValidationError, match="Missing template name"):
            dispatch(["todo", "template", "modify"], {})

    def test_modify_not_found(self, mock_todo_svc):
        """Non-existent template raises."""
        with pytest.raises(CommandValidationError, match="Template not found"):
            dispatch(["todo", "template", "modify", "nonexistent"], {})

    def test_modify_new_name(self, mock_todo_svc):
        """--new-name renames the template."""
        mock_todo_svc.get_template_by_name.return_value = {
            "uuid": "tpl-abc", "name": "old",
        }
        dispatch(
            ["todo", "template", "modify", "old"],
            {"new-name": "new"},
        )
        update_data = mock_todo_svc.update_template.call_args[0][1]
        assert update_data["name"] == "new"

    def test_modify_title_placeholder(self, mock_todo_svc):
        """--title-placeholder updates placeholder."""
        mock_todo_svc.get_template_by_name.return_value = {
            "uuid": "tpl-abc", "name": "daily",
        }
        dispatch(
            ["todo", "template", "modify", "daily"],
            {"title-placeholder": "Updated"},
        )
        update_data = mock_todo_svc.update_template.call_args[0][1]
        assert update_data["title_placeholder"] == "Updated"

    def test_modify_with_fields(self, mock_todo_svc):
        """--text, --file flags add fields to template."""
        mock_todo_svc.get_template_by_name.return_value = {
            "uuid": "tpl-abc", "name": "daily",
        }
        dispatch(
            ["todo", "template", "modify", "daily"],
            {"text": "deadline"},
        )
        update_data = mock_todo_svc.update_template.call_args[0][1]
        assert len(update_data["fields"]) == 1
        assert update_data["fields"][0]["name"] == "deadline"

    def test_modify_no_fields_to_update(self, mock_todo_svc):
        """No flags raises."""
        mock_todo_svc.get_template_by_name.return_value = {
            "uuid": "tpl-abc", "name": "daily",
        }
        with pytest.raises(CommandValidationError, match="No fields to modify"):
            dispatch(["todo", "template", "modify", "daily"], {})

    def test_modify_with_data_loss_warning(self, mock_todo_svc):
        """Removing fields that are in use returns confirm-type response."""
        mock_todo_svc.get_template_by_name.return_value = {
            "uuid": "tpl-abc", "name": "daily",
        }
        mock_todo_svc.template_fields_in_use.return_value = {
            "deadline": 3,  # 3 todos use this field
        }
        result = dispatch(
            ["todo", "template", "modify", "daily"],
            {"text": "newfield"},
        )
        # "deadline" is in use and not in the new fields → data loss warning
        assert result["type"] == "confirm"
        assert "Data Loss Warning" in result["title"]
        # Note: message is a tuple (trailing comma in source), convert to string for assert
        msg = " ".join(str(m) for m in (result.get("message") or []))
        assert "deadline" in msg

    def test_modify_without_data_loss(self, mock_todo_svc):
        """Fields NOT in use are silently replaced."""
        mock_todo_svc.get_template_by_name.return_value = {
            "uuid": "tpl-abc", "name": "daily",
        }
        mock_todo_svc.template_fields_in_use.return_value = {}
        dispatch(
            ["todo", "template", "modify", "daily"],
            {"text": "newfield"},
        )
        update_data = mock_todo_svc.update_template.call_args[0][1]
        assert "fields" in update_data
        assert update_data["fields"][0]["name"] == "newfield"


class TestTodoTemplateDelete:
    def test_delete_missing_name(self, mock_todo_svc):
        """Missing name raises."""
        with pytest.raises(CommandValidationError, match="Missing template name"):
            dispatch(["todo", "template", "delete"], {})

    def test_delete_not_found(self, mock_todo_svc):
        """Non-existent template raises."""
        with pytest.raises(CommandValidationError, match="Template not found"):
            dispatch(["todo", "template", "delete", "nonexistent"], {})

    def test_delete_success(self, mock_todo_svc):
        """Deletes template and returns status."""
        mock_todo_svc.get_template_by_name.return_value = {
            "uuid": "tpl-abc", "name": "daily",
        }
        result = dispatch(["todo", "template", "delete", "daily"], {})
        assert result["type"] == "status"
        assert result["title"] == "Template Deleted"
        assert result["data"]["name"] == "daily"
        mock_todo_svc.delete_template.assert_called_once_with("tpl-abc")
