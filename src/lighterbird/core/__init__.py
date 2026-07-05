"""Core services — re-exported from lightercore where possible.

``lightercore`` is the canonical source for DB, paths, exceptions, CRUD,
and backup.  Keyring, AI provider, and system prompt wrappers remain local.
"""

from lightercore.backup import (
    BackupStrategy,
    BackupTarget,
    add_strategy,
    backup_all,
    backup_all_strategies,
    backup_database,
    copy_to_external,
    export_data,
    get_backup_targets,
    get_strategy,
    import_data,
    list_backups,
    list_strategies,
    prune_backups,
    remove_strategy,
    restore_by_timestamp,
    restore_latest,
    update_strategy,
    verify_strategy_target,
)
from lightercore.backup import (
    load_config as load_backup_config,
)
from lightercore.backup import (
    save_config as save_backup_config,
)
from lightercore.crud import CRUDService
from lightercore.db import LighterbirdDB
from lightercore.exceptions import (
    AIError,
    AmbiguousIDError,
    AuthenticationError,
    ConfigurationError,
    DatabaseError,
    DataError,
    LighterbirdError,
    ProtectedPathError,
    SyncError,
)
from lightercore.paths import cache_dir, config_dir, data_dir, ensure_dirs, state_dir

# Local wrappers (extend lightercore with lighterbird-specific behavior)
from lighterbird.core.backup import backup_config_files, backup_with_strategy

# Local modules (not in lightercore)
from lighterbird.core.keyring import delete_password, get_password, set_password

__all__ = [
    "AIError",
    "AmbiguousIDError",
    "AuthenticationError",
    "BackupStrategy",
    "BackupTarget",
    "CRUDService",
    "ConfigurationError",
    "DataError",
    "DatabaseError",
    "LighterbirdDB",
    "LighterbirdError",
    "ProtectedPathError",
    "SyncError",
    "add_strategy",
    "backup_all",
    "backup_all_strategies",
    "backup_config_files",
    "backup_database",
    "backup_with_strategy",
    "cache_dir",
    "config_dir",
    "copy_to_external",
    "data_dir",
    "delete_password",
    "ensure_dirs",
    "export_data",
    "get_backup_targets",
    "get_password",
    "get_strategy",
    "import_data",
    "list_backups",
    "list_strategies",
    "load_backup_config",
    "prune_backups",
    "remove_strategy",
    "restore_by_timestamp",
    "restore_latest",
    "save_backup_config",
    "set_password",
    "state_dir",
    "update_strategy",
    "verify_strategy_target",
]
