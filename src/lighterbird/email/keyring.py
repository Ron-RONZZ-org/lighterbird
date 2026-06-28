"""Keyring wrapper for email account passwords.

Service pattern: ``lighterbird/email/{account_email}``.
"""

from __future__ import annotations

from lighterbird.core.keyring import get_password as _core_get
from lighterbird.core.keyring import set_password as _core_set
from lighterbird.core.keyring import delete_password as _core_del

_SERVICE_PREFIX = "lighterbird/email"


def get_password(account_email: str) -> str | None:
    """Retrieve account password from system keyring."""
    return _core_get(f"{_SERVICE_PREFIX}/{account_email}", "password")


def set_password(account_email: str, password: str) -> bool:
    """Store account password in system keyring."""
    return _core_set(f"{_SERVICE_PREFIX}/{account_email}", "password", password)


def delete_password(account_email: str) -> bool:
    """Remove account password from system keyring."""
    return _core_del(f"{_SERVICE_PREFIX}/{account_email}", "password")
