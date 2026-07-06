"""Tests for core/keyring.py — System keyring abstraction.

Now delegates to ``lightercore.llm.config``. Mock at the ``keyring``
library level instead of the module level.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lighterbird.core.keyring import delete_password, get_password, set_password

# ── Helper ───────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _store():
    """Provide an in-memory keyring store."""
    store: dict[str, str] = {}

    def set_pw(service: str, key: str, value: str) -> None:
        store[f"{service}:{key}"] = value

    def get_pw(service: str, key: str) -> str | None:
        return store.get(f"{service}:{key}")

    def del_pw(service: str, key: str) -> None:
        store.pop(f"{service}:{key}", None)

    import keyring as _kr

    with patch.object(_kr, "set_password", set_pw):
        with patch.object(_kr, "get_password", get_pw):
            with patch.object(_kr, "delete_password", del_pw):
                yield store


# ── Tests ────────────────────────────────────────────────────────────────────


class TestGetPassword:
    def test_returns_password(self, _store):
        _store["test-svc:test-key"] = "s3cret"
        result = get_password("test-svc", "test-key")
        assert result == "s3cret"

    def test_not_found_returns_none(self):
        result = get_password("test-svc", "unknown")
        assert result is None


class TestSetPassword:
    def test_returns_true_on_success(self, _store):
        result = set_password("test-svc", "test-key", "p4ss")
        assert result is True
        assert _store["test-svc:test-key"] == "p4ss"

    def test_overwrite(self, _store):
        _store["test-svc:test-key"] = "old"
        set_password("test-svc", "test-key", "new")
        assert _store["test-svc:test-key"] == "new"


class TestDeletePassword:
    def test_returns_true_on_success(self, _store):
        _store["test-svc:test-key"] = "val"
        result = delete_password("test-svc", "test-key")
        assert result is True
        assert "test-svc:test-key" not in _store

    def test_delete_nonexistent_is_idempotent(self):
        result = delete_password("test-svc", "no-such-key")
        assert result is True
