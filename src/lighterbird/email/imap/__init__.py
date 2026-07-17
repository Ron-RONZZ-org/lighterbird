"""IMAP sync engine."""

from lighterbird.email.imap.capabilities import IMAPCapabilities, detect_capabilities
from lighterbird.email.imap.client import IMAPClient
from lighterbird.email.imap.connpool import IMAPConnectionError, IMAPConnectionPool
from lighterbird.email.imap.idle import (
    IMAPIdleManager,
    IMAPIdleThread,
    get_imap_idle_manager,
    init_imap_idle_manager,
)
from lighterbird.email.imap.sync import SyncResult, sync_account

__all__ = [
    "IMAPCapabilities",
    "IMAPClient",
    "IMAPConnectionError",
    "IMAPConnectionPool",
    "IMAPIdleManager",
    "IMAPIdleThread",
    "SyncResult",
    "detect_capabilities",
    "get_imap_idle_manager",
    "init_imap_idle_manager",
    "sync_account",
]
