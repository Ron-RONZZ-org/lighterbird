"""Shared fixtures for contacts tests."""

from __future__ import annotations

import pytest


@pytest.fixture
def svc(tmp_path):
    """Return a fresh ContactService with isolated temp DB."""
    from lighterbird.contacts.db import get_db
    from lighterbird.contacts.services import ContactService

    db = get_db(tmp_path / "contacts.db")
    return ContactService(db)
