"""Core services — DB, crypto, keyring, paths, exceptions, CRUD."""

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
]
