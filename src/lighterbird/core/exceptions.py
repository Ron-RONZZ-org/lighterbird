"""Base exception classes for lighterbird.

Forked from A-core's ``A.core.exceptions``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class LighterbirdError(Exception):
    """Base exception for all lighterbird errors."""

    def __init__(self, message: str, **kwargs: Any):
        super().__init__(message)
        self.message = message
        self.details = kwargs


class ConfigurationError(LighterbirdError):
    """Invalid or missing configuration."""


class DatabaseError(LighterbirdError):
    """Database operation failed."""


class DataError(LighterbirdError):
    """Data-layer errors (deleted entries, etc.)."""


class AuthenticationError(LighterbirdError):
    """Credential or authentication failure."""


class SyncError(LighterbirdError):
    """Sync operation failed (IMAP, CalDAV)."""


class AIError(LighterbirdError):
    """LLM provider call failed."""


class ProtectedPathError(LighterbirdError):
    """Raised when attempting to delete a protected directory.

    A directory is *protected* when it (or an ancestor) contains a
    ``.lighterbird-protected`` marker file.
    """

    def __init__(self, path: str | Path, operation: str = "delete"):
        self.path = Path(path)
        self.operation = operation
        super().__init__(
            f"Cannot {operation} protected path: {path}. "
            f"Remove the '.lighterbird-protected' marker file first."
        )
