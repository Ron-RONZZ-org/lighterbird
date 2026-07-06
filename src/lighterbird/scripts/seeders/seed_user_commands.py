"""Seed user_commands.db and demo prompt command files."""

from __future__ import annotations

import os
from pathlib import Path

from lighterbird.scripts.seeders._helpers import _now


def _seed_user_commands(data_dir: Path) -> None:
    """Seed user_commands.db is intentionally left empty for seed."""
    os.environ["LIGHTERBIRD_DATA_DIR"] = str(data_dir)

    from lighterbird.user_commands import db as uc_db
    uc_db.reset_db()
    uc_db.get_db()


def _seed_prompt_commands(data_dir: Path) -> None:
    """Create a demo prompt command file for development/testing.

    Resolves the commands directory from the current ``LIGHTERBIRD_CONFIG_DIR``
    env var (set by ``seed_data_dir``), falling back to ``data_dir / "config"``.
    """
    cfg = Path(os.environ.get("LIGHTERBIRD_CONFIG_DIR", str(data_dir / "config")))
    commands_dir = cfg / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    demo_file = commands_dir / "demo.md"
    if not demo_file.exists():
        demo_file.write_text(
            "# Demo prompt command for testing\n"
            "This is a sample prompt command for testing purposes.\n"
            "The argument passed was: $1\n",
            encoding="utf-8",
        )
