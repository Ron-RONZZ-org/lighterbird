"""Tests for email/filters/sieve.py — SieveManager (network operations mocked)."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.email.filters.sieve import SieveManager, validate_sieve

# `sievelib` may not be installed — skip Parser-based tests if missing
try:
    import sievelib.parser as _sievelib_parser  # noqa: F401
    _HAS_SIEVELIB = True
except ImportError:
    _HAS_SIEVELIB = False


# ── validate_sieve ────────────────────────────────────────────────────────────


class TestValidateSieveExtended:
    def test_valid_sieve_without_library(self):
        """validate_sieve returns (True, '') when sievelib is not installed."""
        is_valid, err = validate_sieve("require [\"fileinto\"];")
        # If sievelib is absent, always returns valid
        assert is_valid is True
        assert err == ""

    @pytest.mark.skipif(not _HAS_SIEVELIB, reason="sievelib not installed")
    def test_invalid_sieve_when_parser_available(self):
        """When sievelib is available, invalid syntax is detected."""
        with patch("sievelib.parser.Parser") as mock_parser_cls:
            instance = MagicMock()
            instance.parse.return_value = False
            instance.error = "Syntax error line 1"
            mock_parser_cls.return_value = instance

            is_valid, err = validate_sieve("invalid content")
            assert is_valid is False
            assert "Syntax error" in err

    def test_parser_import_error_skips_validation(self):
        """When sievelib is not installed, validation is skipped."""
        # Ensure the module is loaded first
        import importlib

        import lighterbird.email.filters.sieve

        # Simulate sievelib not being available
        with patch.dict("sys.modules", {"sievelib.parser": None}, clear=False):
            importlib.reload(lighterbird.email.filters.sieve)
            is_valid, err = lighterbird.email.filters.sieve.validate_sieve("anything")
            assert is_valid is True
            assert err == ""

        # Restore original module state
        importlib.reload(lighterbird.email.filters.sieve)


# ── SieveManager ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _mock_managesieve():
    """Mock the ``managesieve`` module for all SieveManager tests.

    Since ``managesieve`` may not be installed, we inject a fake module
    into ``sys.modules`` before any imports happen.
    """
    mock_mod = MagicMock()
    mock_mod.MANAGESIEVE = MagicMock()
    old = sys.modules.get("managesieve")
    sys.modules["managesieve"] = mock_mod
    yield mock_mod
    if old is not None:
        sys.modules["managesieve"] = old
    else:
        del sys.modules["managesieve"]


@pytest.fixture
def manager():
    return SieveManager("sieve.example.com", 4190, use_tls=True)


class TestSieveManagerInit:
    def test_default_port(self):
        m = SieveManager("host.com")
        assert m.port == 4190
        assert m.use_tls is True

    def test_no_tls(self):
        m = SieveManager("host.com", use_tls=False)
        assert m.use_tls is False

    def test_custom_port(self):
        m = SieveManager("host.com", port=4191)
        assert m.port == 4191


class TestSieveManagerConnect:
    def test_connect_success(self, manager, _mock_managesieve):
        instance = MagicMock()
        instance.login.return_value = "OK"
        _mock_managesieve.MANAGESIEVE.return_value = instance

        manager.connect("user", "pass")
        assert manager._client is not None
        _mock_managesieve.MANAGESIEVE.assert_called_once_with(
            "sieve.example.com", 4190, use_tls=True
        )
        instance.login.assert_called_once_with("", "user", "pass")

    def test_connect_login_failure(self, manager, _mock_managesieve):
        instance = MagicMock()
        instance.login.return_value = "NO"
        instance.response_text = "Authentication failed"
        _mock_managesieve.MANAGESIEVE.return_value = instance

        with pytest.raises(ConnectionError, match="Sieve login failed"):
            manager.connect("user", "wrong")

    def test_connect_network_error(self, manager, _mock_managesieve):
        import socket

        _mock_managesieve.MANAGESIEVE.side_effect = socket.gaierror(
            "Name or service not known"
        )

        with pytest.raises(ConnectionError, match="Sieve connection failed"):
            manager.connect("user", "pass")

    def test_connect_import_error(self, manager):
        """When managesieve library is not installed, raise helpful error.

        The ``_mock_managesieve`` autouse fixture injects a mock module,
        but ``managesieve`` may also be installed in the venv.  We use
        an empty ``ModuleType`` to block the import at the attribute
        level (``from managesieve import MANAGESIEVE`` fails because
        the empty module has no ``MANAGESIEVE`` attribute → Python
        raises ``ImportError``).
        """
        import importlib

        import lighterbird.email.filters.sieve as sieve_mod

        empty_mod = ModuleType("managesieve")
        with patch.dict("sys.modules", {"managesieve": empty_mod}):
            importlib.reload(sieve_mod)

            m = sieve_mod.SieveManager("host.com", 4190, use_tls=True)
            with pytest.raises(ConnectionError, match="managesieve library not installed"):
                m.connect("user", "pass")

        # Restore the autouse fixture's mock for other tests
        importlib.reload(sieve_mod)


class TestSieveManagerOperations:
    """Operations tested with a pre-connected manager (mocked client)."""

    @pytest.fixture
    def connected(self, manager):
        manager._client = MagicMock()
        return manager

    def test_disconnect(self, connected):
        client = connected._client
        connected.disconnect()
        client.logout.assert_called_once()
        assert connected._client is None

    def test_disconnect_no_client(self):
        m = SieveManager("host.com")
        m.disconnect()  # should not raise

    def test_list_scripts(self, connected):
        connected._client.listscripts.return_value = ("OK", [
            ("spam.sieve", True),
            ("vacation.sieve", False),
        ])
        scripts = connected.list_scripts()
        assert len(scripts) == 2
        assert scripts[0]["name"] == "spam.sieve"
        assert scripts[0]["active"] is True
        assert scripts[1]["active"] is False

    def test_list_scripts_no_active_flag(self, connected):
        """Some servers may return tuples without active flag."""
        connected._client.listscripts.return_value = ("OK", [("script.sieve",)])
        scripts = connected.list_scripts()
        assert len(scripts) == 1
        assert scripts[0]["active"] is False

    def test_list_scripts_not_connected(self, manager):
        with pytest.raises(RuntimeError, match="Not connected"):
            manager.list_scripts()

    def test_get_script(self, connected):
        connected._client.getscript.return_value = ("OK", 'require ["fileinto"];')
        content = connected.get_script("spam.sieve")
        assert "require" in content

    def test_get_script_not_connected(self, manager):
        with pytest.raises(RuntimeError, match="Not connected"):
            manager.get_script("x")

    def test_put_script(self, connected):
        connected.put_script("test.sieve", "content")
        connected._client.putscript.assert_called_once_with("test.sieve", "content")

    def test_put_script_not_connected(self, manager):
        with pytest.raises(RuntimeError, match="Not connected"):
            manager.put_script("x", "y")

    def test_delete_script(self, connected):
        connected.delete_script("test.sieve")
        connected._client.deletescript.assert_called_once_with("test.sieve")

    def test_delete_script_not_connected(self, manager):
        with pytest.raises(RuntimeError, match="Not connected"):
            manager.delete_script("x")

    def test_activate_script(self, connected):
        connected.activate_script("active.sieve")
        connected._client.setactive.assert_called_once_with("active.sieve")

    def test_activate_script_not_connected(self, manager):
        with pytest.raises(RuntimeError, match="Not connected"):
            manager.activate_script("x")


class TestSieveManagerContextManager:
    def test_context_manager(self, _mock_managesieve):
        instance = MagicMock()
        instance.login.return_value = "OK"
        _mock_managesieve.MANAGESIEVE.return_value = instance

        with SieveManager("host.com") as m:
            m.connect("user", "pass")
            assert m._client is not None

        # After context exit, client should be disconnected
        instance.logout.assert_called_once()

    def test_context_manager_logout_on_exception(self):
        """Even if an exception occurs, logout should be called."""
        m = SieveManager("host.com")
        mock_client = MagicMock()
        m._client = mock_client
        try:
            with m:
                raise ValueError("test error")
        except ValueError:
            pass
        # After __exit__, _client is None; use saved reference
        mock_client.logout.assert_called_once()
