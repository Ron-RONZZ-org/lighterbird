"""LLM provider — thin wrapper around core providers.

Provides a singleton provider instance with configuration resolved
from keyring and environment. The server layer manages which provider
is "active"; the core providers are stateless.

The system prompt is loaded from the user-editable file at
``~/.config/lighterbird/system_prompt.md`` and automatically prepended
as a ``system`` message to every conversation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from lighterbird.core.ai import ProviderConfig, get_provider as _create_core_provider
from lighterbird.core.keyring import get_password as _get_kr, set_password as _set_kr, delete_password as _del_kr
from lighterbird.core.system_prompt import load_system_prompt, reload_system_prompt

_SERVICE_NAME = "lighterbird-llm"
_CONFIG_ACCOUNT = "active-provider"
_PROFILES_ACCOUNT = "saved-profiles"


def _build_messages(
    message: str,
    context: list[dict] | None = None,
    *,
    system_override: str | None = None,
) -> list[dict]:
    """Build the messages list with system prompt prepended.

    Args:
        message: User message text.
        context: Optional message history (will be placed after system).
        system_override: If set, use this instead of the file-based prompt.

    Returns:
        List of message dicts suitable for the provider API.
    """
    system_content = system_override if system_override is not None else load_system_prompt()
    messages: list[dict] = [{"role": "system", "content": system_content}]
    if context:
        messages.extend(context)
    messages.append({"role": "user", "content": message})
    return messages


class LLMProviderWrapper:
    """Wrapper that manages LLM provider lifecycle.

    Configuration is persisted in the system keyring under the
    ``lighterbird-llm`` service.  Provider instances are created
    on each call (stateless, per AGENTS-core.md).
    """

    def __init__(self) -> None:
        self._config: ProviderConfig | None = None
        self._active_profile_name: str | None = None

    @property
    def config(self) -> ProviderConfig:
        """Get the current provider config (lazy-loaded from keyring)."""
        if self._config is None:
            self._config = self._load_config()
        return self._config

    def is_available(self) -> bool:
        """Check if a provider is configured and ready."""
        cfg = self.config
        if cfg.provider_type == "ollama":
            return True  # tested on first call
        return bool(cfg.api_key)

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

        messages = _build_messages(message, context)
        provider = _create_core_provider(self.config)
        return await provider.chat(messages, stream=stream)

    async def generate_command(
        self,
        message: str,
        command_defs: list[dict],
        context: list[dict] | None = None,
    ) -> dict[str, Any] | None:
        """Ask the LLM to generate a structured command.

        Returns:
            ``{"tokens": [...], "flags": {...}}`` or ``None``.
        """
        if not self.is_available():
            return None

        core_provider = _create_core_provider(self.config)
        result = await core_provider.generate_command(message, command_defs)
        if isinstance(result, dict):
            return result
        return None

    def reload_prompt(self) -> str:
        """Reload the system prompt from disk (for when the user edits it)."""
        return reload_system_prompt()

    # ── Configuration persistence ────────────────────────────────────────

    def configure(self, provider_type: str, **kwargs: Any) -> ProviderConfig:
        """Save provider configuration to keyring and return config.

        Args:
            provider_type: ``"openai"``, ``"deepseek"``, ``"ollama"``, etc.
            **kwargs: Additional config fields (api_key, base_url, model, etc.).

        Returns:
            The active :class:`ProviderConfig`.
        """
        config_data = {
            "provider_type": provider_type,
            "api_key": kwargs.get("api_key", ""),
            "base_url": kwargs.get("base_url", ""),
            "model": kwargs.get("model", ""),
            "temperature": float(kwargs.get("temperature", 0.7)),
            "max_tokens": int(kwargs.get("max_tokens", 2048)),
        }
        import json
        _set_kr(_SERVICE_NAME, _CONFIG_ACCOUNT, json.dumps(config_data))
        self._config = self._load_config()
        return self._config  # type: ignore[return-value]

    def _load_config(self) -> ProviderConfig:
        """Load provider config from keyring or return defaults."""
        raw = _get_kr(_SERVICE_NAME, _CONFIG_ACCOUNT)
        if not raw:
            return ProviderConfig()

        import json
        try:
            data = json.loads(raw)
            return ProviderConfig(
                provider_type=data.get("provider_type", "openai"),
                api_key=data.get("api_key", ""),
                base_url=data.get("base_url", ""),
                model=data.get("model", ""),
                temperature=float(data.get("temperature", 0.7)),
                max_tokens=int(data.get("max_tokens", 2048)),
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            return ProviderConfig()

    def clear_config(self) -> None:
        """Remove provider configuration from keyring."""
        try:
            _del_kr(_SERVICE_NAME, _CONFIG_ACCOUNT)
        except Exception:
            pass
        self._config = None

    # ── Profile management ────────────────────────────────────────────────

    def save_profile(self, name: str, provider_type: str, **kwargs: Any) -> dict:
        """Save a named LLM profile.

        Profiles are stored as a JSON dict keyed by name.
        """
        import json as _json

        raw = _get_kr(_SERVICE_NAME, _PROFILES_ACCOUNT) or "{}"
        try:
            profiles = _json.loads(raw)
        except (_json.JSONDecodeError, ValueError):
            profiles = {}

        profiles[name] = {
            "provider_type": provider_type,
            "api_key": kwargs.get("api_key", ""),
            "base_url": kwargs.get("base_url", ""),
            "model": kwargs.get("model", ""),
            "temperature": float(kwargs.get("temperature", 0.7)),
            "max_tokens": int(kwargs.get("max_tokens", 2048)),
        }
        _set_kr(_SERVICE_NAME, _PROFILES_ACCOUNT, _json.dumps(profiles))
        return profiles[name]

    def list_profiles(self) -> list[dict]:
        """Return all saved profiles (without API keys)."""
        import json as _json

        raw = _get_kr(_SERVICE_NAME, _PROFILES_ACCOUNT) or "{}"
        try:
            profiles = _json.loads(raw)
        except (_json.JSONDecodeError, ValueError):
            return []
        result = []
        for name, data in profiles.items():
            result.append({
                "name": name,
                "provider_type": data.get("provider_type", ""),
                "base_url": data.get("base_url", ""),
                "model": data.get("model", ""),
                "has_api_key": bool(data.get("api_key", "")),
            })
        return result

    def get_profile(self, name: str) -> dict | None:
        """Get a saved profile by name (WITH api_key)."""
        import json as _json

        raw = _get_kr(_SERVICE_NAME, _PROFILES_ACCOUNT) or "{}"
        try:
            profiles = _json.loads(raw)
        except (_json.JSONDecodeError, ValueError):
            return None
        return profiles.get(name)

    def modify_profile(self, name: str, **kwargs: Any) -> dict | None:
        """Partially update a saved profile.

        Args:
            name: Profile name.
            **kwargs: Fields to update (provider_type, api_key, base_url,
                      model, temperature, max_tokens).
                      Empty string for api_key is treated as "keep current".

        Returns:
            The updated profile dict, or None if profile not found.
        """
        import json as _json

        raw = _get_kr(_SERVICE_NAME, _PROFILES_ACCOUNT) or "{}"
        try:
            profiles = _json.loads(raw)
        except (_json.JSONDecodeError, ValueError):
            return None

        if name not in profiles:
            return None

        profile = profiles[name]
        for key in ("provider_type", "base_url", "model"):
            if key in kwargs:
                profile[key] = kwargs[key]
        # api_key requires explicit non-empty value (empty = keep current)
        if "api_key" in kwargs and kwargs["api_key"]:
            profile["api_key"] = kwargs["api_key"]
        if "temperature" in kwargs:
            profile["temperature"] = float(kwargs["temperature"])
        if "max_tokens" in kwargs:
            profile["max_tokens"] = int(kwargs["max_tokens"])

        profiles[name] = profile
        _set_kr(_SERVICE_NAME, _PROFILES_ACCOUNT, _json.dumps(profiles))

        # Return without API key for safety
        return {
            "name": name,
            "provider_type": profile.get("provider_type", ""),
            "base_url": profile.get("base_url", ""),
            "model": profile.get("model", ""),
            "has_api_key": bool(profile.get("api_key", "")),
        }

    def delete_profile(self, name: str) -> bool:
        """Delete a saved profile. Returns True if deleted."""
        import json as _json

        raw = _get_kr(_SERVICE_NAME, _PROFILES_ACCOUNT) or "{}"
        try:
            profiles = _json.loads(raw)
        except (_json.JSONDecodeError, ValueError):
            return False
        if name not in profiles:
            return False
        del profiles[name]
        _set_kr(_SERVICE_NAME, _PROFILES_ACCOUNT, _json.dumps(profiles))
        return True

    @property
    def active_profile_name(self) -> str | None:
        """Return the name of the currently active profile, if any."""
        return self._active_profile_name

    def switch_to_profile(self, name: str) -> ProviderConfig | None:
        """Activate a saved profile. Returns the config or None."""
        profile = self.get_profile(name)
        if not profile:
            return None
        cfg = self.configure(
            provider_type=profile["provider_type"],
            api_key=profile.get("api_key", ""),
            base_url=profile.get("base_url", ""),
            model=profile.get("model", ""),
            temperature=profile.get("temperature", 0.7),
            max_tokens=profile.get("max_tokens", 2048),
        )
        self._active_profile_name = name
        return cfg


# Singleton
_provider: LLMProviderWrapper | None = None


def get_provider() -> LLMProviderWrapper:
    """Get the singleton LLM provider wrapper."""
    global _provider
    if _provider is None:
        _provider = LLMProviderWrapper()
    return _provider
