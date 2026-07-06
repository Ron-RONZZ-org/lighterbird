"""Tests for server/llm/provider.py — LLM provider wrapper."""

from __future__ import annotations

from lightercore.llm.utils import build_messages

from lighterbird.server.llm.provider import LLMProviderWrapper

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _fresh_provider():
    """Return a fresh LLMProviderWrapper (bypassing the singleton)."""
    from lighterbird.server import deps

    deps.reset_services()  # clean state for a fresh singleton
    return LLMProviderWrapper()


def _mock_keyring_store(monkeypatch) -> dict[str, str]:
    """Set up an in-memory keyring mock and return the store dict."""
    store: dict[str, str] = {}

    def set_pw(service: str, key: str, value: str) -> None:
        store[f"{service}:{key}"] = value

    def get_pw(service: str, key: str) -> str | None:
        return store.get(f"{service}:{key}")

    def del_pw(service: str, key: str) -> None:
        store.pop(f"{service}:{key}", None)

    import keyring as _kr

    monkeypatch.setattr(_kr, "set_password", set_pw)
    monkeypatch.setattr(_kr, "get_password", get_pw)
    monkeypatch.setattr(_kr, "delete_password", del_pw)
    return store


# ── build_messages tests ─────────────────────────────────────────────────────


class TestBuildMessages:
    """build_messages now comes from lightercore — smoke tests."""

    def test_adds_system_and_user(self):
        messages = build_messages("hello")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "hello"

    def test_with_context(self):
        context = [{"role": "assistant", "content": "Hi"}]
        messages = build_messages("hello", context=context)
        assert len(messages) == 3
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"

    def test_with_system_override(self):
        messages = build_messages("hello", system_override="Custom")
        assert messages[0]["content"] == "Custom"


# ── is_available tests ───────────────────────────────────────────────────────


class TestIsAvailable:
    def test_not_configured_returns_false(self, monkeypatch):
        _mock_keyring_store(monkeypatch)
        provider = _fresh_provider()
        assert provider.is_available() is False

    def test_with_api_key(self, monkeypatch):
        store = _mock_keyring_store(monkeypatch)
        store["lighterbird-llm:active-config"] = (
            '{"provider_type": "openai", "api_key": "sk-test"}'
        )
        provider = _fresh_provider()
        assert provider.is_available() is True

    def test_ollama(self, monkeypatch):
        store = _mock_keyring_store(monkeypatch)
        store["lighterbird-llm:active-config"] = (
            '{"provider_type": "ollama", "api_key": ""}'
        )
        provider = _fresh_provider()
        assert provider.is_available() is True

    def test_clear_config(self, monkeypatch):
        store = _mock_keyring_store(monkeypatch)
        store["lighterbird-llm:active-config"] = (
            '{"provider_type": "openai", "api_key": "sk-test"}'
        )
        provider = _fresh_provider()
        provider.clear_config()
        assert provider.is_available() is False


# ── Profile management tests ─────────────────────────────────────────────────


class TestProfileManagement:
    def test_save_and_list(self, monkeypatch):
        store = _mock_keyring_store(monkeypatch)
        provider = _fresh_provider()
        provider.save_profile("work", "openai", api_key="sk-work", model="gpt-4")
        profiles = provider.list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "work"
        assert profiles[0]["has_api_key"] is True

    def test_get_profile_returns_api_key(self, monkeypatch):
        store = _mock_keyring_store(monkeypatch)
        provider = _fresh_provider()
        provider.save_profile("secret", "openai", api_key="sk-secret")
        profile = provider.get_profile("secret")
        assert profile is not None
        assert profile["api_key"] == "sk-secret"

    def test_delete(self, monkeypatch):
        store = _mock_keyring_store(monkeypatch)
        provider = _fresh_provider()
        provider.save_profile("test", "openai")
        assert provider.delete_profile("test") is True
        assert provider.delete_profile("nonexistent") is False

    def test_modify(self, monkeypatch):
        store = _mock_keyring_store(monkeypatch)
        provider = _fresh_provider()
        provider.save_profile("work", "openai", model="gpt-3.5")
        result = provider.modify_profile("work", model="gpt-4")
        assert result is not None
        assert result["model"] == "gpt-4"
        assert provider.modify_profile("nonexistent") is None
