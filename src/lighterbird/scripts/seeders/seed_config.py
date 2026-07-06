"""Seed LLM provider config and backup config."""

from __future__ import annotations

import json
from pathlib import Path

from lighterbird.scripts.seeders._helpers import _parse_dot_dev


def _seed_llm_config(creds: dict[str, str]) -> None:
    """Configure the LLM provider from .dev credentials if not already set."""
    from lighterbird.core.keyring import get_password, set_password

    api_key = creds.get("TEST_DEEPSEEK_APIKEY", "")
    if not api_key:
        return

    configured = get_password("lighterbird-llm", "active-provider")
    if configured:
        return

    config = {
        "provider_type": "openai",
        "api_key": api_key,
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "temperature": 0.7,
        "max_tokens": 4096,
    }
    set_password("lighterbird-llm", "active-provider", json.dumps(config))


def _seed_backup_config(data_dir: Path) -> None:
    """Create a basic backup config so backup commands don't error."""
    from lighterbird.core.backup import BackupStrategy, save_config

    save_config({"version": 3, "strategies": [
        BackupStrategy(
            id="default",
            label="Default",
            interval_minutes=0,
            max_copies=10,
            target="local",
            enabled=True,
        ).to_dict()
    ]})
