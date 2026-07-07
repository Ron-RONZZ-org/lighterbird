"""Flag sync service — orchestrates push (local→server) and pull (server→local).

Push is handled by :class:`BacklogService` processing the ``_sync_backlog``
table.  Pull is handled by :class:`FlagPuller` using CONDSTORE/QRESYNC
extensions when the server supports them.

This service is the coordinator: it decides what to do when and in what
order.  Concrete operations are delegated to sub-services.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class FlagSyncService:
    """Orchestrate push and pull of email flags to/from IMAP servers.

    Args:
        backlog: BacklogService instance for push operations.
        pool: IMAP connection pool (optional, for pull operations).
        folder_mapper: Folder name resolution service (optional).
        flag_puller: FlagPuller instance (optional, created lazily).
    """

    def __init__(
        self,
        db: Any,
        backlog: Any | None = None,
        pool: Any | None = None,
        folder_mapper: Any | None = None,
        flag_puller: Any | None = None,
    ):
        self.db = db
        self._backlog = backlog
        self._pool = pool
        self._folder_mapper = folder_mapper
        self._flag_puller = flag_puller

    def push_pending(self, account_email: str | None = None) -> int:
        """Push pending local flag changes to the IMAP server.

        Delegates to :meth:`BacklogService.process_all`.

        Args:
            account_email: If set, only process backlog for this account.

        Returns:
            Number of backlog entries successfully pushed.
        """
        if self._backlog is None:
            logger.warning("[flag_sync] No backlog service configured")
            return 0
        return self._backlog.process_all(account_email=account_email)

    @property
    def flag_puller(self) -> Any:
        """Lazy-initialized FlagPuller."""
        if self._flag_puller is None:
            from lighterbird.email.sync.flag_pull import FlagPuller
            self._flag_puller = FlagPuller(self.db)
        return self._flag_puller

    def pull_changes(self, account_email: str,
                     folders: list[str] | None = None) -> dict[str, int]:
        """Pull server-side flag changes for known messages.

        Uses CONDSTORE via :class:`FlagPuller` when available.

        Args:
            account_email: Account to pull changes for.
            folders: Folders to check.  If None, checks all folders.

        Returns:
            Dict mapping folder name to count of local updates applied.
        """
        if self._flag_puller is not None:
            return self._flag_puller.pull_changes(account_email, folders)
        if self.db:
            from lighterbird.email.sync.flag_pull import FlagPuller
            puller = FlagPuller(self.db)
            return puller.pull_changes(account_email, folders)
        return {}


__all__ = ["FlagSyncService"]
