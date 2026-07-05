"""Shared fixtures for journal tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def svc(tmp_path):
    """Return a fresh JournalService with isolated temp DB."""
    from lighterbird.journal.db import get_db
    from lighterbird.journal.services import JournalService

    db = get_db(tmp_path / "journal.db")
    return JournalService(db)
