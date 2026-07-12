"""Seed LLM provider config and backup config."""

from __future__ import annotations

from pathlib import Path

from lighterbird.scripts.seeders._helpers import _parse_dot_dev


def _seed_llm_config(creds: dict[str, str]) -> None:
    """Configure the LLM provider from .dev credentials if not already set."""
    from lightercore.llm.config import (
        ProviderConfig,
        load_active_config,
        save_active_config,
    )

    api_key = creds.get("TEST_DEEPSEEK_APIKEY", "")
    if not api_key:
        return

    configured = load_active_config("lighterbird-llm")
    if configured is not None and configured.is_available():
        return

    cfg = ProviderConfig(
        provider_type="openai",
        api_key=api_key,
        base_url="https://api.deepseek.com",
        model="deepseek-v4-flash",
        embedding_model="",
        temperature=0.7,
        max_tokens=4096,
    )
    save_active_config("lighterbird-llm", cfg)


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
