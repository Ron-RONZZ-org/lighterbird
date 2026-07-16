# Backup System Analysis

## Autodiscovery Implementation (replaces hardcoded list)

Following A-core's `backup_targets.py` pattern, backup targets are now
auto-discovered by scanning `data_dir()` for `*.db` files and `config_dir()`
for `*.md` files at backup time. No hardcoded list, no registration needed.

Key API (in `src/lighterbird/core/backup.py`):
- `BackupTarget` dataclass — path, category ("data"/"config"), module, label
- `get_backup_targets(category=None)` — returns all discovered BackupTargets
- `_known_db_paths()` / `_known_config_files()` — legacy wrappers that delegate
  to `get_backup_targets()`

Benefits:
- Future module that places `<name>.db` in `data_dir()` is automatically
  included — no need to update backup code
- Config files (`*.md` in `config_dir()`) similarly auto-discovered
- Matchs A-core's convention-based fallback pattern

## Bug Fixed (previous)