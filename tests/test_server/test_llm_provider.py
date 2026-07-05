"""Tests for server/llm/provider.py — LLM provider wrapper."""

from __future__ import annotations

from lighterbird.server.llm.provider import (
    LLMProviderWrapper,
    _build_messages,
)


def _fresh_provider():
    """Return a fresh LLMProviderWrapper (bypassing the singleton)."""
    from lighterbird.server import deps
    deps._email_service = None  # not needed but cleans state
    return LLMProviderWrapper()


class TestBuildMessages:
    def test_adds_system_and_user(self):
        messages = _build_messages("hello")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "hello"

    def test_with_context(self):
        context = [{"role": "assistant", "content": "Hi"}]
        messages = _build_messages("hello", context=context)
        assert len(messages) == 3
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"

    def test_with_system_override(self):
        messages = _build_messages("hello", system_override="Custom")
        assert messages[0]["content"] == "Custom"


class TestIsAvailable:
    def test_not_configured_returns_false(self, monkeypatch):
        """A fresh provider with no config should be unavailable."""
        monkeypatch.setattr(
            "lighterbird.server.llm.provider._get_kr",
            lambda *a: None,
        )
        provider = _fresh_provider()
        assert provider.is_available() is False

    def test_with_api_key(self, monkeypatch):
        monkeypatch.setattr(
            "lighterbird.server.llm.provider._get_kr",
            lambda *a: '{"provider_type": "openai", "api_key": "sk-test"}',
        )
        provider = _fresh_provider()
        assert provider.is_available() is True

    def test_ollama(self, monkeypatch):
        monkeypatch.setattr(
            "lighterbird.server.llm.provider._get_kr",
            lambda *a: '{"provider_type": "ollama", "api_key": ""}',
        )
        provider = _fresh_provider()
        assert provider.is_available() is True

    def test_clear_config(self, monkeypatch):
        monkeypatch.setattr("lighterbird.server.llm.provider._get_kr", lambda *a: None)
        monkeypatch.setattr("lighterbird.server.llm.provider._del_kr", lambda *a: None)
        provider = _fresh_provider()
        provider.clear_config()
        assert provider.is_available() is False


class TestProfileManagement:
    def test_save_and_list(self, monkeypatch):
        stored: list[str | None] = [None]

        def mock_set(*args):
            stored[0] = args[2]

        monkeypatch.setattr("lighterbird.server.llm.provider._get_kr",
                            lambda *a: stored[0] or "{}")
        monkeypatch.setattr("lighterbird.server.llm.provider._set_kr", mock_set)

        provider = _fresh_provider()
        provider.save_profile("work", "openai", api_key="sk-work", model="gpt-4")
        profiles = provider.list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "work"
        assert profiles[0]["has_api_key"] is True

    def test_get_profile_returns_api_key(self, monkeypatch):
        stored: list[str | None] = [None]

        def mock_set(*args):
            stored[0] = args[2]

        monkeypatch.setattr("lighterbird.server.llm.provider._get_kr",
                            lambda *a: stored[0] or "{}")
        monkeypatch.setattr("lighterbird.server.llm.provider._set_kr", mock_set)

        provider = _fresh_provider()
        provider.save_profile("secret", "openai", api_key="sk-secret")
        profile = provider.get_profile("secret")
        assert profile is not None
        assert profile["api_key"] == "sk-secret"

    def test_delete(self, monkeypatch):
        stored: list[str | None] = [None]

        def mock_set(*args):
            stored[0] = args[2]

        monkeypatch.setattr("lighterbird.server.llm.provider._get_kr",
                            lambda *a: stored[0] or "{}")
        monkeypatch.setattr("lighterbird.server.llm.provider._set_kr", mock_set)

        provider = _fresh_provider()
        provider.save_profile("test", "openai")
        assert provider.delete_profile("test") is True
        assert provider.delete_profile("nonexistent") is False

    def test_modify(self, monkeypatch):
        stored: list[str | None] = [None]

        def mock_set(*args):
            stored[0] = args[2]

        monkeypatch.setattr("lighterbird.server.llm.provider._get_kr",
                            lambda *a: stored[0] or "{}")
        monkeypatch.setattr("lighterbird.server.llm.provider._set_kr", mock_set)

        provider = _fresh_provider()
        provider.save_profile("work", "openai", model="gpt-3.5")
        result = provider.modify_profile("work", model="gpt-4")
        assert result is not None
        assert result["model"] == "gpt-4"
        assert provider.modify_profile("nonexistent") is None
