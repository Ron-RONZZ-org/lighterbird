# AGENTS-core.md — Core Module Agent Instructions

## Summary

Re-exports from [lightercore](../../lightercore) for database (``LighterbirdDB``), path resolution (``data_dir``, ``config_dir``, etc.), exception hierarchy, CRUD service base, and strategy-based backup. Keeps local wrappers for keyring access, AI provider, and system prompt management.

## Key Files

- ``db.py`` — Re-exports ``LighterbirdDB`` from ``lightercore.db``
- ``paths.py`` — Re-exports XDG path resolution from ``lightercore.paths``
- ``exceptions.py`` — Re-exports exception hierarchy from ``lightercore.exceptions``
- ``crud.py`` — Re-exports ``CRUDService`` from ``lightercore.crud``
- ``backup.py`` — Re-exports from ``lightercore.backup`` + lighterbird-specific wrappers (``backup_config_files``, ``backup_with_strategy``)
- ``keyring.py`` — System keyring password management (local)
- ``ai.py`` — LLM provider abstraction (local, wraps openai library)
- ``system_prompt.py`` — User-editable system prompt management (local)
- ``cowrite_style.py`` — Co-writing style configuration (local)
- ``config_defaults.py`` — Startup seeding of default config files from ``_CONFIG_DEFAULTS`` registry (``system_prompt.md``, ``cowrite_style.md``). Called once from ``server/app.py:lifespan``.

## Key Behavior

- All canonical implementations live in [lightercore](../../lightercore). Improvements should be made there, not in these wrappers.
- The ``__init__.py`` re-exports the public API from lightercore + local modules.
