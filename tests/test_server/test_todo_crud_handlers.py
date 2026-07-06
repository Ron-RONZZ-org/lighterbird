"""Tests for todo_crud command handlers — add, view, done, modify, delete."""

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
    svc.create.return_value = {"uuid": "td-123", "title": "Test"}
    svc.get.return_value = None
    svc.get_with_children.return_value = None
    svc.get_dependencies.return_value = []
    svc.get_blocked_tasks.return_value = []
    svc.get_attachments.return_value = []
    svc.get_template_by_name.return_value = None
    deps._services["todo"] = svc
    return svc


class TestTodoAdd:
    def test_add_missing_title(self, mock_todo_svc):
        """Missing title raises CommandValidationError."""
        with pytest.raises(CommandValidationError, match="Missing todo title"):
            dispatch(["todo", "add"], {})

    def test_add_success(self, mock_todo_svc):
        """Creates a todo with title."""
        mock_todo_svc.create.return_value = {
            "uuid": "td-abc", "title": "Buy milk",
        }
        result = dispatch(["todo", "add", "Buy milk"], {})
        assert result["type"] == "status"
        assert result["title"] == "Todo Added"
        assert result["data"]["title"] == "Buy milk"
        create_data = mock_todo_svc.create.call_args[0][0]
        assert create_data["title"] == "Buy milk"

    def test_add_with_due_and_priority(self, mock_todo_svc):
        """--due and --priority flags are passed through."""
        dispatch(
            ["todo", "add", "Task"],
            {"due": "2024-12-31", "priority": "1"},
        )
        create_data = mock_todo_svc.create.call_args[0][0]
        assert create_data["due_date"] == "2024-12-31"
        assert create_data["priority"] == "1"

    def test_add_with_description(self, mock_todo_svc):
        """--description flag is passed through."""
        dispatch(["todo", "add", "Task"], {"description": "Do the thing"})
        create_data = mock_todo_svc.create.call_args[0][0]
        assert create_data["description"] == "Do the thing"

    def test_add_with_tags(self, mock_todo_svc):
        """--tags flag creates labels and passes tags to create."""
        dispatch(["todo", "add", "Task"], {"tags": "work,urgent"})
        assert mock_todo_svc.create_label.call_count == 2
        create_data = mock_todo_svc.create.call_args[0][0]
        assert create_data["_tags"] == ["work", "urgent"]

    def test_add_with_tags_label_exists(self, mock_todo_svc):
        """ValueError from create_label (duplicate) is silently caught."""
        mock_todo_svc.create_label.side_effect = ValueError("exists")
        dispatch(["todo", "add", "Task"], {"tags": "work"})
        # Should not raise

    def test_add_with_parent(self, mock_todo_svc):
        """--parent flag resolves parent UUID."""
        mock_todo_svc.get.return_value = {"uuid": "parent-123"}
        dispatch(["todo", "add", "Subtask"], {"parent": "parent-123"})
        create_data = mock_todo_svc.create.call_args[0][0]
        assert create_data["parent_uuid"] == "parent-123"

    def test_add_parent_not_found(self, mock_todo_svc):
        """Non-existent parent raises."""
        mock_todo_svc.get.return_value = None
        with pytest.raises(
            CommandValidationError, match="Parent todo not found"
        ):
            dispatch(["todo", "add", "Subtask"], {"parent": "nonexistent"})

    def test_add_with_dependency(self, mock_todo_svc):
        """--dependency flag resolves dependency UUIDs."""
        mock_todo_svc.get.side_effect = [
            {"uuid": "dep-123"},  # first call for dependency
            None,  # subsequent calls
        ]
        # Actually get might be called multiple times - let me just check
        # that the create call includes _depends_on
        def get_side_effect(uuid):
            if uuid == "dep-123":
                return {"uuid": "dep-123"}
            return None
        mock_todo_svc.get.side_effect = get_side_effect

        dispatch(["todo", "add", "Task"], {"dependency": "dep-123"})
        create_data = mock_todo_svc.create.call_args[0][0]
        assert create_data["_depends_on"] == ["dep-123"]

    def test_add_dependency_not_found(self, mock_todo_svc):
        """Non-existent dependency raises."""
        with pytest.raises(
            CommandValidationError, match="Dependency todo not found"
        ):
            dispatch(["todo", "add", "Task"], {"dependency": "nonexistent"})

    def test_add_with_template(self, mock_todo_svc):
        """--template flag resolves template and sets template_uuid."""
        mock_todo_svc.get_template_by_name.return_value = {
            "uuid": "tpl-123", "name": "daily",
        }
        dispatch(["todo", "add", "Daily Standup"], {"template": "daily"})
        create_data = mock_todo_svc.create.call_args[0][0]
        assert create_data["template_uuid"] == "tpl-123"

    def test_add_template_not_found(self, mock_todo_svc):
        """Non-existent template raises."""
        with pytest.raises(
            CommandValidationError, match="Template not found"
        ):
            dispatch(["todo", "add", "Task"], {"template": "nonexistent"})

    def test_add_multi_word_title(self, mock_todo_svc):
        """Multiple remaining tokens are joined as title."""
        dispatch(["todo", "add", "Buy", "milk", "and", "eggs"], {})
        create_data = mock_todo_svc.create.call_args[0][0]
        assert create_data["title"] == "Buy milk and eggs"


class TestTodoView:
    def test_view_missing_uuid(self, mock_todo_svc):
        """Missing UUID raises."""
        with pytest.raises(CommandValidationError, match="Missing todo UUID"):
            dispatch(["todo", "view"], {})

    def test_view_not_found(self, mock_todo_svc):
        """Non-existent UUID raises."""
        with pytest.raises(CommandValidationError, match="Todo not found"):
            dispatch(["todo", "view", "nonexistent"], {})

    def test_view_success(self, mock_todo_svc):
        """Returns status with full todo data including children, deps, attachments."""
        mock_todo_svc.get_with_children.return_value = {
            "uuid": "td-abc", "title": "My Task",
        }
        mock_todo_svc.get_dependencies.return_value = [
            {"uuid": "dep-1", "title": "Prerequisite"},
        ]
        mock_todo_svc.get_blocked_tasks.return_value = []
        mock_todo_svc.get_attachments.return_value = [
            {"name": "file.pdf"},
        ]
        result = dispatch(["todo", "view", "td-abc"], {})
        assert result["type"] == "status"
        assert result["title"] == "My Task"
        assert len(result["data"]["dependencies"]) == 1
        assert len(result["data"]["attachments"]) == 1
        mock_todo_svc.get_with_children.assert_called_once_with("td-abc")
        mock_todo_svc.get_dependencies.assert_called_once_with("td-abc")
        mock_todo_svc.get_blocked_tasks.assert_called_once_with("td-abc")
        mock_todo_svc.get_attachments.assert_called_once_with("td-abc")


class TestTodoDone:
    def test_done_missing_uuid(self, mock_todo_svc):
        """Missing UUID raises."""
        with pytest.raises(CommandValidationError, match="Missing todo UUID"):
            dispatch(["todo", "done"], {})

    def test_done_success(self, mock_todo_svc):
        """Marks todo as done and returns status."""
        result = dispatch(["todo", "done", "td-abc"], {})
        assert result["type"] == "status"
        assert result["title"] == "Todo(s) Done"
        assert "td-abc" in result["data"]["done"]
        mock_todo_svc.mark_done.assert_called_once_with("td-abc")

    def test_done_multiple(self, mock_todo_svc):
        """Multiple UUIDs can be done at once."""
        result = dispatch(["todo", "done", "td-abc", "td-def"], {})
        assert len(result["data"]["done"]) == 2
        assert mock_todo_svc.mark_done.call_count == 2

    def test_done_skips_exceptions(self, mock_todo_svc):
        """Exceptions from mark_done are caught and skipped."""
        mock_todo_svc.mark_done.side_effect = [
            None,
            Exception("fail"),
            None,
        ]
        result = dispatch(
            ["todo", "done", "td-ok1", "td-bad", "td-ok2"], {}
        )
        assert result["data"]["done"] == ["td-ok1", "td-ok2"]


class TestTodoModify:
    def test_modify_missing_uuid(self, mock_todo_svc):
        """Missing UUID raises."""
        with pytest.raises(CommandValidationError, match="Missing todo UUID"):
            dispatch(["todo", "modify"], {})

    def test_modify_no_fields(self, mock_todo_svc):
        """No update flags raises."""
        with pytest.raises(CommandValidationError, match="No fields to modify"):
            dispatch(["todo", "modify", "td-abc"], {})

    def test_modify_success(self, mock_todo_svc):
        """Updates fields and returns status."""
        result = dispatch(
            ["todo", "modify", "td-abc"],
            {"title": "New Title", "description": "Updated desc"},
        )
        assert result["type"] == "status"
        assert result["title"] == "Todo Modified"
        mock_todo_svc.update.assert_called_once()
        update_data = mock_todo_svc.update.call_args[0][1]
        assert update_data["title"] == "New Title"
        assert update_data["description"] == "Updated desc"

    def test_modify_with_due_and_priority(self, mock_todo_svc):
        """--due and --priority flags are passed to update."""
        dispatch(
            ["todo", "modify", "td-abc"],
            {"due": "2024-12-31", "priority": "3"},
        )
        update_data = mock_todo_svc.update.call_args[0][1]
        assert update_data["due_date"] == "2024-12-31"
        assert update_data["priority"] == "3"

    def test_modify_with_status(self, mock_todo_svc):
        """--status flag is passed to update."""
        dispatch(["todo", "modify", "td-abc"], {"status": "in_progress"})
        update_data = mock_todo_svc.update.call_args[0][1]
        assert update_data["status"] == "in_progress"

    def test_modify_parent_to_none(self, mock_todo_svc):
        """--parent none clears parent_uuid."""
        dispatch(["todo", "modify", "td-abc"], {"parent": "none"})
        update_data = mock_todo_svc.update.call_args[0][1]
        assert update_data["parent_uuid"] is None

    def test_modify_parent_not_found(self, mock_todo_svc):
        """Non-existent parent raises."""
        with pytest.raises(
            CommandValidationError, match="Parent todo not found"
        ):
            dispatch(["todo", "modify", "td-abc"], {"parent": "nonexistent"})

    def test_modify_with_tags(self, mock_todo_svc):
        """--tags flag updates tags on the todo."""
        dispatch(
            ["todo", "modify", "td-abc"],
            {"tags": "work,home"},
        )
        update_data = mock_todo_svc.update.call_args[0][1]
        assert update_data["_tags"] == ["work", "home"]

    def test_modify_tags_empty_clears(self, mock_todo_svc):
        """--tags '' clears all tags."""
        dispatch(
            ["todo", "modify", "td-abc"],
            {"tags": ""},
        )
        update_data = mock_todo_svc.update.call_args[0][1]
        assert update_data["_tags"] == []


class TestTodoDelete:
    def test_delete_missing_uuid(self, mock_todo_svc):
        """Missing UUID raises."""
        with pytest.raises(
            CommandValidationError, match="Missing todo UUID"
        ):
            dispatch(["todo", "delete"], {})

    def test_delete_success(self, mock_todo_svc):
        """Deletes todo and returns status."""
        result = dispatch(["todo", "delete", "td-abc"], {})
        assert result["type"] == "status"
        assert result["title"] == "Todo(s) Deleted"
        assert "td-abc" in result["data"]["removed"]
        mock_todo_svc.delete.assert_called_once_with("td-abc")

    def test_delete_multiple(self, mock_todo_svc):
        """Multiple UUIDs can be deleted at once."""
        result = dispatch(["todo", "delete", "td-abc", "td-def"], {})
        assert len(result["data"]["removed"]) == 2
        assert mock_todo_svc.delete.call_count == 2

    def test_delete_skips_exceptions(self, mock_todo_svc):
        """Exceptions from delete are caught and skipped."""
        mock_todo_svc.delete.side_effect = [
            None,
            Exception("fail"),
            None,
        ]
        result = dispatch(
            ["todo", "delete", "td-ok1", "td-bad", "td-ok2"], {}
        )
        assert result["data"]["removed"] == ["td-ok1", "td-ok2"]
