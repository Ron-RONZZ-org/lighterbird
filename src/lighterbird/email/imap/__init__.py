"""IMAP sync engine."""

from lighterbird.email.imap.capabilities import IMAPCapabilities, detect_capabilities
from lighterbird.email.imap.client import IMAPClient
from lighterbird.email.imap.connpool import IMAPConnectionError, IMAPConnectionPool
from lighterbird.email.imap.idle import IMAPIdleManager, IMAPIdleThread
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
    "sync_account",
]
