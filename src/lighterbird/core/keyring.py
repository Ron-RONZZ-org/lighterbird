"""System keyring abstraction for lighterbird.

Wraps the ``keyring`` library with graceful fallback when unavailable.
Passwords are stored in the OS credential manager, never in SQLite.

Forked from A-core's ``A.core.keyring``.
"""

from __future__ import annotations


def _keyring_available() -> bool:
    try:
        import keyring  # noqa: F401
        return True
    except ImportError:
        return False


def get_password(service: str, key: str) -> str | None:
    """Retrieve a password from the system keyring.

    Args:
        service: Service name (e.g. ``"lighterbird/{account_uuid}"``)
        key: Key within the service (e.g. ``"password"``)

    Returns:
        The stored password, or ``None`` if not found or keyring unavailable.
    """
    if not _keyring_available():
        return None
    try:
        import keyring
        return keyring.get_password(service, key)
    except Exception:
        return None


def set_password(service: str, key: str, password: str) -> bool:
    """Store a password in the system keyring.

    Returns:
        ``True`` if stored successfully.
    """
    if not _keyring_available():
        return False
    try:
        import keyring
        keyring.set_password(service, key, password)
        return True
    except Exception:
        return False


def delete_password(service: str, key: str) -> bool:
    """Remove a password from the system keyring. Idempotent."""
    if not _keyring_available():
        return False
    try:
        import keyring
        keyring.delete_password(service, key)
        return True
    except keyring.errors.PasswordDeleteError:
        return True
    except Exception:
        return False
