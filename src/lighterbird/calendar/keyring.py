"""Keyring wrapper for calendar passwords.

Service pattern: ``lighterbird/calendar/{calendar_uuid}``.
"""

from __future__ import annotations

from lighterbird.core.keyring import delete_password as _core_del
from lighterbird.core.keyring import get_password as _core_get
from lighterbird.core.keyring import set_password as _core_set

_SERVICE_PREFIX = "lighterbird/calendar"


def get_password(calendar_uuid: str) -> str | None:
    """Retrieve calendar password from system keyring."""
    return _core_get(f"{_SERVICE_PREFIX}/{calendar_uuid}", "password")


def set_password(calendar_uuid: str, password: str) -> bool:
    """Store calendar password in system keyring."""
    return _core_set(f"{_SERVICE_PREFIX}/{calendar_uuid}", "password", password)


def delete_password(calendar_uuid: str) -> bool:
    """Remove calendar password from system keyring."""
    return _core_del(f"{_SERVICE_PREFIX}/{calendar_uuid}", "password")
