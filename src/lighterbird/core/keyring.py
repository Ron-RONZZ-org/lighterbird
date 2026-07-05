"""System keyring abstraction for lighterbird.

Wraps the ``keyring`` library with graceful fallback when unavailable.
Passwords are stored in the OS credential manager, never in SQLite.

Forked from A-core's ``A.core.keyring``.
"""

from __future__ import annotations

import importlib.util
import logging

logger = logging.getLogger(__name__)

_keyring_available: bool = importlib.util.find_spec("keyring") is not None

if _keyring_available:
    import keyring  # type: ignore[assignment]
else:
    keyring = None  # type: ignore[assignment]


def get_password(service: str, key: str) -> str | None:
    """Retrieve a password from the system keyring.

    Args:
        service: Service name (e.g. ``"lighterbird/email/{email}"``)
        key: Key within the service (e.g. ``"password"``)

    Returns:
        The stored password, or ``None`` if not found or keyring unavailable.
    """
    if not _keyring_available:
        return None
    try:
        return keyring.get_password(service, key)  # type: ignore[union-attr]
    except Exception as exc:
        logger.warning("Keyring get_password failed for %s/%s: %s", service, key, exc)
        return None


def set_password(service: str, key: str, password: str) -> bool:
    """Store a password in the system keyring.

    Returns:
        ``True`` if stored successfully.
    """
    if not _keyring_available:
        return False
    try:
        keyring.set_password(service, key, password)  # type: ignore[union-attr]
        return True
    except Exception as exc:
        logger.warning("Keyring set_password failed for %s/%s: %s", service, key, exc)
        return False


def delete_password(service: str, key: str) -> bool:
    """Remove a password from the system keyring. Idempotent."""
    if not _keyring_available:
        return False
    try:
        keyring.delete_password(service, key)  # type: ignore[union-attr]
        return True
    except keyring.errors.PasswordDeleteError:
        return True
    except Exception as exc:
        logger.warning("Keyring delete_password failed for %s/%s: %s", service, key, exc)
        return False
