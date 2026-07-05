"""Tests for core/keyring.py — System keyring abstraction.

We mock at the module level to avoid depending on actual system keyring.
The module uses ``importlib.util.find_spec("keyring")`` at import time,
so we patch both ``_keyring_available`` and the ``keyring`` module functions.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lighterbird.core.keyring import delete_password, get_password, set_password


# Create a proper exception class for mocking PasswordDeleteError
class _MockPasswordDeleteError(Exception):
    pass


@pytest.fixture(autouse=True)
def _mock_keyring():
    """Mock the keyring module and mark it as available."""
    with patch("lighterbird.core.keyring._keyring_available", True):
        with patch("lighterbird.core.keyring.keyring") as mock:
            # Attach a proper exception to mock.keyring.errors
            mock.errors.PasswordDeleteError = _MockPasswordDeleteError
            yield mock


class TestGetPassword:
    def test_returns_password(self, _mock_keyring):
        _mock_keyring.get_password.return_value = "s3cret"
        result = get_password("test-svc", "test-key")
        assert result == "s3cret"
        _mock_keyring.get_password.assert_called_once_with(
            "test-svc", "test-key"
        )

    def test_not_found_returns_none(self, _mock_keyring):
        _mock_keyring.get_password.return_value = None
        result = get_password("test-svc", "unknown")
        assert result is None

    def test_exception_returns_none_and_logs(self, _mock_keyring):
        _mock_keyring.get_password.side_effect = RuntimeError("busy")
        result = get_password("test-svc", "test-key")
        assert result is None


class TestSetPassword:
    def test_returns_true_on_success(self, _mock_keyring):
        result = set_password("test-svc", "test-key", "p4ss")
        assert result is True
        _mock_keyring.set_password.assert_called_once_with(
            "test-svc", "test-key", "p4ss"
        )

    def test_returns_false_on_exception(self, _mock_keyring):
        _mock_keyring.set_password.side_effect = RuntimeError("denied")
        result = set_password("test-svc", "test-key", "p4ss")
        assert result is False


class TestDeletePassword:
    def test_returns_true_on_success(self, _mock_keyring):
        result = delete_password("test-svc", "test-key")
        assert result is True
        _mock_keyring.delete_password.assert_called_once_with(
            "test-svc", "test-key"
        )

    def test_password_delete_error_returns_true(self, _mock_keyring):
        """Delete errors are quietly swallowed (idempotent)."""
        _mock_keyring.delete_password.side_effect = _MockPasswordDeleteError()
        result = delete_password("test-svc", "test-key")
        assert result is True

    def test_other_exception_returns_false(self, _mock_keyring):
        _mock_keyring.delete_password.side_effect = RuntimeError("fail")
        result = delete_password("test-svc", "test-key")
        assert result is False


# keyring-unavailable path tests
class TestKeyringNotAvailable:
    def test_get_returns_none(self):
        with patch("lighterbird.core.keyring._keyring_available", False):
            assert get_password("svc", "key") is None

    def test_set_returns_false(self):
        with patch("lighterbird.core.keyring._keyring_available", False):
            assert set_password("svc", "key", "pw") is False

    def test_delete_returns_false(self):
        with patch("lighterbird.core.keyring._keyring_available", False):
            assert delete_password("svc", "key") is False
