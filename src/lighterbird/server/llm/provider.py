"""LLM provider — thin wrapper around core providers.

Provides a singleton provider instance with configuration resolved
from keyring and environment. The server layer manages which provider
is "active"; the core providers are stateless.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from lighterbird.core.ai import ProviderConfig, get_provider
from lighterbird.core.keyring import get_password as _get_kr, set_password as _set_kr, delete_password as _del_kr

_SERVICE_NAME = "lighterbird-llm"
_CONFIG_ACCOUNT = "active-provider"


class LLMProviderWrapper:
    """Wrapper that manages LLM provider lifecycle.

    Configuration is persisted in the system keyring under the
    ``lighterbird-llm`` service.  Provider instances are created
    on each call (stateless, per AGENTS-core.md).
    """

    def __init__(self) -> None:
        self._config: ProviderConfig | None = None

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

        messages = list(context or [])
        messages.append({"role": "user", "content": message})

        provider = get_provider(self.config)
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

        messages = list(context or [])
        messages.append({"role": "user", "content": message})
        provider = get_provider(self.config)
        result = await provider.generate_command(message, command_defs)
        if isinstance(result, dict):
            return result
        return None

    # ── Configuration persistence ────────────────────────────────────────

    def configure(self, provider_type: str, **kwargs: Any) -> ProviderConfig:
        """Save provider configuration to keyring and return config.

        Args:
            provider_type: ``"openai"`` or ``"ollama"``.
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


# Singleton
_provider: LLMProviderWrapper | None = None


def get_provider() -> LLMProviderWrapper:
    """Get the singleton LLM provider wrapper."""
    global _provider
    if _provider is None:
        _provider = LLMProviderWrapper()
    return _provider
