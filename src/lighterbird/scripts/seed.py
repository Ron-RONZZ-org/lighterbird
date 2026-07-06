"""Seed lighterbird databases with test data from ``.dev`` credentials.

Usage::

    from lighterbird.scripts.seed import seed_data_dir
    seed_data_dir("/tmp/lighterbird-test")

This module orchestrates domain-specific seeders imported from the
``seeders`` sub-package.  Each seeder creates and populates one database
file (email, calendar, contacts, todo, journal, letters, profiles,
user_commands) along with auxiliary configuration (LLM, backup, prompt
commands).

See the individual modules in ``seeders/`` for implementation details.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from lighterbird.scripts.seeders import (
    _seed_backup_config,
    _seed_calendar,
    _seed_contacts,
    _seed_email,
    _seed_journal,
    _seed_letters,
    _seed_llm_config,
    _seed_profiles,
    _seed_prompt_commands,
    _seed_todo,
    _seed_user_commands,
    _parse_dot_dev,
)


# ── Public API ──────────────────────────────────────────────────────────────


def seed_data_dir(
    target_dir: str | Path,
    dot_dev_path: str | Path | None = None,
) -> None:
    """Initialize and populate all lighterbird databases in *target_dir*.

    Creates eight database files (email, calendar, contacts, todo, journal,
    letters, profiles, user_commands) with schemas initialized and seed
    data inserted. Also creates a demo prompt command file for ``/*`` testing.

    Passwords for test accounts are stored in the system keyring.
    The LLM provider is auto-configured from ``.dev`` if not already set.

    Args:
        target_dir: Directory to create database files in (created if missing).
        dot_dev_path: Path to the ``.dev`` file with test credentials.
            If ``None``, auto-discovers from the project root.
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)

    creds = _parse_dot_dev(dot_dev_path)

    # Set env so singletons (profiles, user_commands) resolve correctly
    os.environ["LIGHTERBIRD_DATA_DIR"] = str(target)
    os.environ["LIGHTERBIRD_CONFIG_DIR"] = str(target / "config")

    _seed_email(target, creds)
    _seed_calendar(target, creds)
    _seed_contacts(target)
    _seed_todo(target)
    _seed_journal(target)
    _seed_letters(target)
    _seed_profiles(target)
    _seed_user_commands(target)
    _seed_prompt_commands(target)
    _seed_llm_config(creds)
    _seed_backup_config(target)


def seed_test_seed_7z(output_path: str | Path) -> Path:
    """Generate a test-seed.7z archive from .dev credentials.

    Uses a temporary directory to generate all seed data, then creates a
    7z archive containing the databases.  Cleans up the temp dir.
    """
    from lighterbird.core.backup import BackupStrategy
    from lighterbird.core.backup import _create_strategy_archive as _create_archive

    tmp = Path(tempfile.mkdtemp(prefix="lighterbird-seed-"))
    data_tmp = tmp / "data"
    config_tmp = tmp / "config"
    data_tmp.mkdir(parents=True, exist_ok=True)
    config_tmp.mkdir(parents=True, exist_ok=True)

    try:
        seed_data_dir(data_tmp)
        strategy = BackupStrategy(id="default", label="Default").to_dict()
        archive = _create_archive(strategy)
        if archive:
            dst = Path(output_path)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(archive), str(dst))
            return dst
        raise RuntimeError("Seed archive creation returned None")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
