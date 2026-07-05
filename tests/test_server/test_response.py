"""Tests for server/command/response.py — Response normalization helpers."""

from __future__ import annotations

from lighterbird.server.command.response import normalize_todo, normalize_todo_for_db


class TestNormalizeTodo:
    def test_removes_computed_priority(self):
        result = normalize_todo({"title": "test", "_computed_priority": 42})
        assert result == {"title": "test"}

    def test_no_computed_priority(self):
        result = normalize_todo({"title": "test", "priority": 3})
        assert result == {"title": "test", "priority": 3}

    def test_empty_dict(self):
        assert normalize_todo({}) == {}

    def test_recursively_normalizes_children(self):
        todo = {
            "title": "parent",
            "children": [
                {"title": "child1", "_computed_priority": 5},
                {"title": "child2"},
            ],
        }
        result = normalize_todo(todo)
        assert result["title"] == "parent"
        assert "_computed_priority" not in result
        assert len(result["children"]) == 2
        assert "_computed_priority" not in result["children"][0]
        assert result["children"][0]["title"] == "child1"


class TestNormalizeTodoForDb:
    def test_returns_same_dict(self):
        todo = {"title": "test", "priority": 3}
        result = normalize_todo_for_db(todo)
        assert result is todo  # same object, no transformation
