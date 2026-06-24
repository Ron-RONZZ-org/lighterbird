"""Core services — DB, crypto, keyring, paths, exceptions, CRUD, backup."""

from lighterbird.core.db import LighterbirdDB
from lighterbird.core.paths import data_dir, config_dir, cache_dir, state_dir, ensure_dirs
from lighterbird.core.keyring import get_password, set_password, delete_password
from lighterbird.core.crud import CRUDService
from lighterbird.core.exceptions import (
    LighterbirdError,
    ConfigurationError,
    DatabaseError,
    DataError,
    AuthenticationError,
    SyncError,
    AIError,
    ProtectedPathError,
)
from lighterbird.core.backup import (
    backup_database,
    backup_all,
    backup_config_files,
    copy_to_external,
    list_backups,
    restore_latest,
    restore_by_timestamp,
    prune_backups,
    export_data,
    import_data,
    load_config as load_backup_config,
    save_config as save_backup_config,
)

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
    "backup_database",
    "backup_all",
    "backup_config_files",
    "copy_to_external",
    "list_backups",
    "restore_latest",
    "restore_by_timestamp",
    "prune_backups",
    "export_data",
    "import_data",
    "load_backup_config",
    "save_backup_config",
]
