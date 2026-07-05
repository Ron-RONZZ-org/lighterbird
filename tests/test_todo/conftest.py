"""Shared fixtures for todo tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def svc(tmp_path):
    """Return a fresh TodoService with isolated temp DB.

    Also sets ``LIGHTERBIRD_DATA_DIR`` so the shared ``TagService``
    (tags.db) lands in the same temp directory.
    """
    os.environ.setdefault("LIGHTERBIRD_DATA_DIR", str(tmp_path))
    from lighterbird.todo.db import get_db
    from lighterbird.todo.services import TodoService

    db = get_db(tmp_path / "todo.db")
    return TodoService(db)
