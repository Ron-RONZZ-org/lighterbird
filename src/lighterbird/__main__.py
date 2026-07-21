"""Entry point for `python -m lighterbird` — start the web server.

On first run in development, auto-configures the LLM provider
from ``.dev`` if present and no provider is configured yet.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Module-level guard: once configured, skip on reload (uvicorn --reload
# re-imports this module on every file change). Without this guard,
# the keyring lookup runs on every reload.
_auto_configured: bool = False


def _auto_configure_from_dev() -> None:
    """Seed the LLM provider config from a ``.dev`` file in the project root.

    Only applies when no provider is configured yet (fresh install).
    Only runs once per process — subsequent imports (reloads) are no-ops.
    """
    global _auto_configured
    if _auto_configured:
        return
    _auto_configured = True

    from lighterllm.llm.config import (
        ProviderConfig,
        load_active_config,
        save_active_config,
    )

    configured = load_active_config("lighterbird-llm")
    if configured is not None and configured.is_available():
        return  # already configured

    dev_path = Path(__file__).resolve().parent.parent.parent / ".dev"
    if not dev_path.exists():
        return

    lines = dev_path.read_text(encoding="utf-8").splitlines()
    dev_vars: dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            dev_vars[key.strip()] = val.strip().strip('"').strip("'")

    api_key = dev_vars.get("TEST_DEEPSEEK_APIKEY", "")
    if api_key:
        cfg = ProviderConfig(
            provider_type="openai",
            api_key=api_key,
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
            temperature=0.7,
            max_tokens=4096,
        )
        save_active_config("lighterbird-llm", cfg)
        logger.info("[lighterbird] Auto-configured LLM provider from .dev (DeepSeek)")


_auto_configure_from_dev()

from lighterbird.server.app import main  # noqa: E402

main()
