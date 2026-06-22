"""IMAP sync engine."""

from lighterbird.email.imap.client import IMAPClient
from lighterbird.email.imap.sync import sync_account, SyncResult

__all__ = ["IMAPClient", "sync_account", "SyncResult"]
