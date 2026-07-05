"""Shared fixtures for todo tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def svc(tmp_path):
    """Return a fresh TodoService with isolated temp DB."""
    from lighterbird.todo.db import get_db
    from lighterbird.todo.services import TodoService

    db = get_db(tmp_path / "todo.db")
    return TodoService(db)
