"""Entry point for `python -m lighterbird` — start the web server.

On first run in development, auto-configures the LLM provider
from ``.dev`` if present and no provider is configured yet.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _auto_configure_from_dev() -> None:
    """Seed the LLM provider config from a ``.dev`` file in the project root.

    Only applies when no provider is configured yet (fresh install).
    """
    from lighterbird.core.keyring import get_password, set_password

    configured = get_password("lighterbird-llm", "active-provider")
    if configured:
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
        config = {
            "provider_type": "openai",
            "api_key": api_key,
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "temperature": 0.7,
            "max_tokens": 4096,
        }
        set_password("lighterbird-llm", "active-provider", json.dumps(config))
        logger.info("[lighterbird] Auto-configured LLM provider from .dev (DeepSeek)")


_auto_configure_from_dev()

from lighterbird.server.app import main  # noqa: E402

main()
