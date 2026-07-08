"""LLM provider — thin wrapper around core providers.

Configuration and named profiles are persisted in the system keyring via
``lightercore.llm`` modules.  Core provider instances are created on each
call (stateless, per AGENTS-core.md).

The system prompt is loaded from a user-editable file via
:mod:`lighterbird.core.system_prompt`.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from lightercore.exceptions import AIError
from lightercore.llm import ProviderConfig
from lightercore.llm.base import ChatResult
from lightercore.llm.config import (
    clear_active_config,
    load_active_config,
    save_active_config,
)
from lightercore.llm.profiles import ProfileManager
from lightercore.llm.utils import build_messages

from lighterbird.core.ai import get_provider as _create_core_provider
from lighterbird.core.system_prompt import load_system_prompt, reload_system_prompt

logger = logging.getLogger(__name__)

_SERVICE_NAME = "lighterbird-llm"


class LLMProviderWrapper:
    """Wrapper that manages LLM provider lifecycle.

    Configuration is persisted in the system keyring under the
    ``lighterbird-llm`` service.  Provider instances are created
    on each call (stateless, per AGENTS-core.md).
    """

    def __init__(self) -> None:
        self._config: ProviderConfig | None = None
        self._profile_mgr = ProfileManager(_SERVICE_NAME)
        self._active_profile_name: str | None = None

    @property
    def config(self) -> ProviderConfig:
        """Get the current provider config (lazy-loaded from keyring)."""
        if self._config is None:
            loaded = load_active_config(_SERVICE_NAME)
            self._config = loaded if loaded is not None else ProviderConfig()
        return self._config

    def is_available(self) -> bool:
        """Check if a provider is configured and ready."""
        return self.config.is_available()

    async def chat(
        self,
        message: str,
        context: list[dict] | None = None,
        stream: bool = False,
    ) -> str | AsyncIterator[str]:
        """Send a chat message and return/stream the response.

        The system prompt (from the user-editable file) is automatically
        prepended as a ``system`` message.

        Args:
            message: User message text.
            context: Optional message history.
            stream: If True, return an async iterator of tokens.

        Returns:
            Response string or async token iterator.
        """
        if not self.is_available():
            if stream:

                async def _placeholder() -> AsyncIterator[str]:
                    yield "LLM not configured. Use ! commands or configure a provider."

                return _placeholder()
            return "LLM not configured. Use ! commands or configure a provider."

        messages = build_messages(
            message,
            context=context,
            default_system=load_system_prompt(),
        )
        provider = _create_core_provider(self.config)
        try:
            return await provider.chat(messages, stream=stream)
        except AIError:
            if stream:

                async def _err_placeholder() -> AsyncIterator[str]:
                    yield "LLM request failed. Check your provider configuration."

                return _err_placeholder()
            return "LLM request failed. Check your provider configuration."

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        tool_choice: str | None = None,
    ) -> ChatResult:
        """Send a chat completion with tool-calling support.

        Delegates to the core provider's :meth:`~lightercore.llm.base.BaseLLMProvider.chat_with_tools`.
        The system prompt is automatically prepended.
        """
        core = _create_core_provider(self.config)
        try:
            return await core.chat_with_tools(messages, tools, tool_choice=tool_choice)
        except AIError as exc:
            logger.warning("AIError in chat_with_tools: %s", exc)
            return ChatResult(content="LLM request failed. Check your provider configuration.")
        except Exception:
            logger.exception("Unexpected error in chat_with_tools")
            return ChatResult(content="LLM request failed.")

    def reload_prompt(self) -> str:
        """Reload the system prompt from disk (for when the user edits it)."""
        return reload_system_prompt()

    # ── Configuration persistence ────────────────────────────────────────

    def configure(self, provider_type: str, **kwargs: Any) -> ProviderConfig:
        """Save provider configuration to keyring and return config.

        Args:
            provider_type: ``"openai"``, ``"deepseek"``, ``"ollama"``, etc.
            **kwargs: Additional config fields (api_key, base_url, model,
                      embedding_model, etc.).

        Returns:
            The active :class:`ProviderConfig`.
        """
        config = ProviderConfig(
            provider_type=provider_type,
            api_key=kwargs.get("api_key", ""),
            base_url=kwargs.get("base_url", ""),
            model=kwargs.get("model", ""),
            embedding_model=kwargs.get("embedding_model", ""),
            temperature=float(kwargs.get("temperature", 0.7)),
            max_tokens=int(kwargs.get("max_tokens", 2048)),
        )
        save_active_config(_SERVICE_NAME, config)
        self._config = config
        return config

    def clear_config(self) -> None:
        """Remove provider configuration from keyring."""
        clear_active_config(_SERVICE_NAME)
        self._config = None

    # ── Profile management ────────────────────────────────────────────────

    def save_profile(self, name: str, provider_type: str, **kwargs: Any) -> dict:
        """Save a named LLM profile.

        Profiles are stored as a JSON dict keyed by name in keyring.
        """
        config = ProviderConfig(
            provider_type=provider_type,
            api_key=kwargs.get("api_key", ""),
            base_url=kwargs.get("base_url", ""),
            model=kwargs.get("model", ""),
            embedding_model=kwargs.get("embedding_model", ""),
            temperature=float(kwargs.get("temperature", 0.7)),
            max_tokens=int(kwargs.get("max_tokens", 2048)),
        )
        self._profile_mgr.save(name, config)
        return config.to_dict()

    def list_profiles(self) -> list[dict]:
        """Return all saved profiles (without API keys)."""
        return self._profile_mgr.list()

    def get_profile(self, name: str) -> dict | None:
        """Get a saved profile by name (WITH api_key)."""
        cfg = self._profile_mgr.get(name)
        if cfg is None:
            return None
        return cfg.to_dict()

    def modify_profile(self, name: str, **kwargs: Any) -> dict | None:
        """Partially update a saved profile.

        Args:
            name: Profile name.
            **kwargs: Fields to update (provider_type, api_key, base_url,
                      model, temperature, max_tokens).
                      Empty string for api_key is treated as "keep current".

        Returns:
            The updated profile dict (without API key), or None if not found.
        """
        config = self._profile_mgr.modify(name, **kwargs)
        if config is None:
            return None
        # Return without API key for safety (matches lighterbird convention)
        return {
            "name": name,
            "provider_type": config.provider_type,
            "base_url": config.base_url,
            "model": config.model,
            "has_api_key": bool(config.api_key),
        }

    def delete_profile(self, name: str) -> bool:
        """Delete a saved profile. Returns True if deleted."""
        return self._profile_mgr.delete(name)

    @property
    def active_profile_name(self) -> str | None:
        """Return the name of the currently active profile, if any."""
        return self._active_profile_name

    def switch_to_profile(self, name: str) -> ProviderConfig | None:
        """Activate a saved profile. Returns the config or None."""
        config = self._profile_mgr.switch_to(name)
        if config is None:
            return None
        # switch_to already calls save_active_config — just update cache
        self._config = config
        self._active_profile_name = name
        return config


# Singleton
_provider: LLMProviderWrapper | None = None


def get_provider() -> LLMProviderWrapper:
    """Get the singleton LLM provider wrapper."""
    global _provider
    if _provider is None:
        _provider = LLMProviderWrapper()
    return _provider
