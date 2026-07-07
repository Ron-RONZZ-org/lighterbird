"""Per-account IMAP connection pool.

Provides connection reuse for backlog processing and sync operations.
Single-user app — max one connection per account.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class IMAPConnectionError(Exception):
    """Raised when a connection cannot be established or reused."""


class IMAPConnectionPool:
    """Per-account IMAP connection pool.

    Maintains at most one connection per account.  Connections are
    lazily created and reused.  Idle connections are closed after
    ``max_idle_seconds`` of inactivity.

    Thread-safe: uses a per-account lock for connection operations.
    """

    def __init__(self, max_idle_seconds: int = 300):
        self._connections: dict[str, Any] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._last_used: dict[str, float] = {}
        self._max_idle = max_idle_seconds
        self._global_lock = threading.Lock()

    def acquire(self, account_email: str, host: str, port: int,
                use_ssl: bool, username: str, password: str) -> Any:
        """Get a connected IMAPClient for the account.

        Reuses an existing connection if available and still alive.
        Otherwise creates a new connection.

        Args:
            account_email: Account identifier.
            host: IMAP server host.
            port: IMAP server port.
            use_ssl: Whether to use SSL.
            username: IMAP username.
            password: IMAP password.

        Returns:
            A connected IMAPClient instance.

        Raises:
            IMAPConnectionError: If connection fails.
        """
        from lighterbird.email.imap.client import IMAPClient

        # Get or create per-account lock
        with self._global_lock:
            if account_email not in self._locks:
                self._locks[account_email] = threading.Lock()

        acct_lock = self._locks[account_email]
        with acct_lock:
            existing = self._connections.get(account_email)
            if existing is not None:
                try:
                    # Quick check if the connection is alive via NOOP
                    existing.conn.noop()
                    self._last_used[account_email] = time.monotonic()
                    logger.debug("[connpool] Reused connection for %s", account_email)
                    return existing
                except Exception:
                    # Connection is dead — remove it and create new
                    logger.debug("[connpool] Connection dead for %s, reconnecting", account_email)
                    self._discard_unlocked(account_email)

            # Create new connection
            client = IMAPClient(host, port, use_ssl)
            try:
                client.connect(username, password)
            except Exception as e:
                raise IMAPConnectionError(
                    f"Failed to connect {username}@{host}:{port} — {e}"
                ) from e

            self._connections[account_email] = client
            self._last_used[account_email] = time.monotonic()
            logger.debug("[connpool] New connection for %s", account_email)
            return client

    def release(self, account_email: str) -> None:
        """Return a connection to the pool (marks as available for reuse).

        The connection stays open for future ``acquire()`` calls.
        Call this instead of ``disconnect()`` when you want to reuse.
        """
        if account_email in self._connections:
            self._last_used[account_email] = time.monotonic()

    def discard(self, account_email: str) -> None:
        """Close and remove a connection from the pool.

        Call this after an auth failure or permanent error.
        """
        with self._global_lock:
            lock = self._locks.get(account_email)
        if lock:
            with lock:
                self._discard_unlocked(account_email)

    def _discard_unlocked(self, account_email: str) -> None:
        """Discard connection (call under lock)."""
        client = self._connections.pop(account_email, None)
        self._last_used.pop(account_email, None)
        if client:
            try:
                client.disconnect()
            except Exception:
                pass

    def cleanup_idle(self) -> int:
        """Close connections idle longer than ``max_idle_seconds``.

        Returns:
            Number of connections closed.
        """
        now = time.monotonic()
        closed = 0
        with self._global_lock:
            idle_accounts = [
                email for email, last in self._last_used.items()
                if now - last > self._max_idle
            ]
        for email in idle_accounts:
            lock = self._locks.get(email)
            if lock and lock.acquire(timeout=2):
                try:
                    if email in self._connections:
                        self._discard_unlocked(email)
                        closed += 1
                finally:
                    lock.release()
        if closed:
            logger.info("[connpool] Closed %d idle connections", closed)
        return closed

    def close_all(self) -> int:
        """Close all connections in the pool.

        Returns:
            Number of connections closed.
        """
        closed = 0
        with self._global_lock:
            emails = list(self._connections.keys())
        for email in emails:
            lock = self._locks.get(email)
            if lock and lock.acquire(timeout=2):
                try:
                    self._discard_unlocked(email)
                    closed += 1
                finally:
                    lock.release()
        logger.info("[connpool] Closed all %d connections", closed)
        return closed


__all__ = ["IMAPConnectionError", "IMAPConnectionPool"]
