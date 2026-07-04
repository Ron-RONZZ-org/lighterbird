"""Core services — re-exported from lightercore where possible.

``lightercore`` is the canonical source for DB, paths, exceptions, CRUD,
and backup.  Keyring, AI provider, and system prompt wrappers remain local.
"""

from lightercore.db import LighterbirdDB
from lightercore.paths import data_dir, config_dir, cache_dir, state_dir, ensure_dirs
from lightercore.crud import CRUDService
from lightercore.exceptions import (
    LighterbirdError,
    ConfigurationError,
    DatabaseError,
    DataError,
    AuthenticationError,
    SyncError,
    AIError,
    ProtectedPathError,
    AmbiguousIDError,
)
from lightercore.backup import (
    BackupStrategy,
    BackupTarget,
    backup_all,
    backup_all_strategies,
    backup_database,
    copy_to_external,
    get_backup_targets,
    list_backups,
    list_strategies,
    get_strategy,
    add_strategy,
    update_strategy,
    remove_strategy,
    verify_strategy_target,
    restore_latest,
    restore_by_timestamp,
    prune_backups,
    export_data,
    import_data,
    load_config as load_backup_config,
    save_config as save_backup_config,
)

# Local modules (not in lightercore)
from lighterbird.core.keyring import get_password, set_password, delete_password

# Local wrappers (extend lightercore with lighterbird-specific behavior)
from lighterbird.core.backup import backup_config_files, backup_with_strategy

__all__ = [
    "LighterbirdDB",
    "data_dir",
    "config_dir",
    "cache_dir",
    "state_dir",
    "ensure_dirs",
    "get_password",
    "set_password",
    "delete_password",
    "CRUDService",
    "LighterbirdError",
    "ConfigurationError",
    "DatabaseError",
    "DataError",
    "AuthenticationError",
    "SyncError",
    "AIError",
    "ProtectedPathError",
    "AmbiguousIDError",
    "BackupStrategy",
    "BackupTarget",
    "backup_all",
    "backup_all_strategies",
    "backup_config_files",
    "backup_database",
    "backup_with_strategy",
    "copy_to_external",
    "get_backup_targets",
    "list_backups",
    "list_strategies",
    "get_strategy",
    "add_strategy",
    "update_strategy",
    "remove_strategy",
    "verify_strategy_target",
    "restore_latest",
    "restore_by_timestamp",
    "prune_backups",
    "export_data",
    "import_data",
    "load_backup_config",
    "save_backup_config",
]
