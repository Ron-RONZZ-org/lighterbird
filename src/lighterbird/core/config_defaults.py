"""Default config file seeding — create shipped defaults on startup.

On server startup the :func:`seed_config_defaults` function creates any
missing config files with their shipped default content, so the user has
a starting point for customisation.  This is the "eager" counterpart to
the lazy auto-seeding in individual ``load_*`` functions.

Adding a new user-editable config file with a shipped default:
    1. Define the default content constant in the relevant module.
    2. Add a ``(filename, default)`` entry to :data:`_CONFIG_DEFAULTS`.
    3. The startup seeding and any ``load_*`` lazy fallback are automatic.
"""

from __future__ import annotations

import logging

from lightercore.paths import config_dir

from lighterbird.core.cowrite_style import (
    DEFAULT_COWRITE_STYLE,
    DEFAULT_COWRITE_STYLE_EMAIL,
    DEFAULT_COWRITE_STYLE_JOURNAL,
    DEFAULT_COWRITE_STYLE_LETTER,
    DEFAULT_COWRITE_STYLE_TODO,
)
from lighterbird.core.system_prompt import DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# ── Default config files registry ─────────────────────────────────────────

_CONFIG_DEFAULTS: dict[str, str] = {
    "system_prompt.md": DEFAULT_SYSTEM_PROMPT,
    "cowrite_style.md": DEFAULT_COWRITE_STYLE,
    "cowrite_style_email.md": DEFAULT_COWRITE_STYLE_EMAIL,
    "cowrite_style_journal.md": DEFAULT_COWRITE_STYLE_JOURNAL,
    "cowrite_style_todo.md": DEFAULT_COWRITE_STYLE_TODO,
    "cowrite_style_letter.md": DEFAULT_COWRITE_STYLE_LETTER,
}
"""Registry of config filenames → default content.

Add new entries here when introducing a new user-editable config file
with a shipped default.  The :func:`seed_config_defaults` function
reads this dict on startup and creates any missing files.

Entries are created under ``~/.config/lighterbird/``.
"""


def seed_config_defaults() -> None:
    """Create default config files if they do not already exist.

    Called once on server startup (from ``lifespan``).  For each known
    config file, if the file is missing, it is created with its shipped
    default content so the user has a starting point for customisation.

    All write failures are logged as warnings and silently swallowed —
    a failure to seed a config file should never prevent the server from
    starting.  The corresponding ``load_*`` functions will fall back to
    lazy seeding when the file is first accessed.
    """
    base = config_dir()
    for filename, default in _CONFIG_DEFAULTS.items():
        path = base / filename
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    continue  # file exists with content — respect user edits
            except OSError:
                pass  # unreadable file — try to reseed below

        # Auto-seed with shipped default
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default, encoding="utf-8")
            logger.info("Seeded default config: %s", path)
        except OSError as exc:
            logger.warning("Failed to seed %s: %s", path, exc)


__all__ = [
    "seed_config_defaults",
]
