"""IMAP IDLE manager — push notification via RFC 2177.

Provides per-account IDLE threads that monitor for new messages and
flag changes.  Calls back into the main worker to trigger incremental
syncs.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Maximum time to stay in IDLE before re-issuing (29 min, RFC 2177 recommends < 30)
_IDLE_TIMEOUT = 29 * 60

# Exponential backoff for reconnection
_BASE_RETRY_DELAY = 30  # seconds
_MAX_RETRY_DELAY = 300  # 5 minutes
_MAX_RECONNECT_ATTEMPTS = 10


class IMAPIdleThread:
    """Single-account IDLE thread.

    Connects to the IMAP server, SELECTs INBOX, and enters IDLE loop.
    On server push notifications (EXISTS, FETCH FLAGS), calls the
    callback.  Handles reconnection with exponential backoff.

    Args:
        account_email: Account to monitor.
        host: IMAP server host.
        port: IMAP server port.
        use_ssl: Whether to use SSL.
        username: IMAP username.
        password: IMAP password.
        on_notification: Callback ``(account_email, folder, event_type)``
                         where event_type is ``'exists'`` or ``'flags'``.
    """

    def __init__(
        self,
        account_email: str,
        host: str,
        port: int,
        use_ssl: bool,
        username: str,
        password: str,
        on_notification: Callable[[str, str, str], None],
    ):
        self.account_email = account_email
        self._host = host
        self._port = port
        self._use_ssl = use_ssl
        self._username = username
        self._password = password
        self._on_notification = on_notification
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_heartbeat: float = 0.0
        self._reconnect_count = 0
        self._connected = False

    def start(self) -> None:
        """Start the IDLE thread."""
        if self._thread and self._thread.is_alive():
            logger.warning("[idle] Thread already running for %s", self.account_email)
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"idle-{self.account_email[:16]}",
            daemon=True,
        )
        self._thread.start()
        logger.info("[idle] Started IDLE thread for %s", self.account_email)

    def stop(self, timeout: float = 3.0) -> None:
        """Signal the IDLE thread to stop and join.

        Args:
            timeout: Max seconds to wait for the thread to finish.
        """
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("[idle] Thread for %s did not stop within %.1fs",
                               self.account_email, timeout)
        logger.info("[idle] Stopped IDLE thread for %s", self.account_email)

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def status(self) -> dict[str, Any]:
        return {
            "account_email": self.account_email,
            "connected": self._connected,
            "alive": self.is_alive,
            "last_heartbeat": datetime.fromtimestamp(
                self._last_heartbeat, tz=UTC
            ).isoformat() if self._last_heartbeat else None,
            "reconnects": self._reconnect_count,
        }

    def _run(self) -> None:
        """Main IDLE loop with reconnection."""
        while not self._stop_event.is_set():
            try:
                self._run_idle_loop()
            except Exception as exc:
                logger.warning(
                    "[idle] IDLE loop error for %s: %s",
                    self.account_email, exc,
                )
            if self._stop_event.is_set():
                break
            # Exponential backoff before reconnect
            delay = min(
                _BASE_RETRY_DELAY * (2 ** self._reconnect_count),
                _MAX_RETRY_DELAY,
            )
            self._reconnect_count += 1
            if self._reconnect_count > _MAX_RECONNECT_ATTEMPTS:
                logger.error(
                    "[idle] Gave up on %s after %d reconnection attempts",
                    self.account_email, _MAX_RECONNECT_ATTEMPTS,
                )
                break
            logger.info(
                "[idle] Reconnecting %s in %ds (attempt %d/%d)",
                self.account_email, delay,
                self._reconnect_count, _MAX_RECONNECT_ATTEMPTS,
            )
            self._stop_event.wait(delay)

    def _run_idle_loop(self) -> None:
        """Connect, SELECT INBOX, and handle IDLE events."""
        from lighterbird.email.imap.client import IMAPClient

        # Detect whether server supports IDLE
        client = IMAPClient(self._host, self._port, self._use_ssl)
        try:
            client.connect(self._username, self._password)
            self._connected = True
            self._reconnect_count = 0
            self._last_heartbeat = time.monotonic()

            if not client.capabilities.has_idle:
                logger.info(
                    "[idle] Server for %s does not support IDLE, skipping",
                    self.account_email,
                )
                return

            # SELECT INBOX
            ok, _uidvalidity, _modseq = client.select_folder_ex(
                "INBOX", readonly=True,
            )
            if not ok:
                logger.warning("[idle] Cannot SELECT INBOX for %s", self.account_email)
                return

            while not self._stop_event.is_set():
                # Enter IDLE
                typ, data = client.conn._simple_command("IDLE")
                if typ != "OK":
                    logger.warning("[idle] IDLE not OK for %s: %s",
                                   self.account_email, typ)
                    break

                # Tell server we're waiting
                client.conn.send(b"DONE\r\n")
                client.conn.send(b"IDLE\r\n")  # Re-enter IDLE

                self._last_heartbeat = time.monotonic()

                # Check for stop signal (short poll)
                if self._stop_event.wait(30):  # Check every 30s
                    client.conn.send(b"DONE\r\n")
                    break

                # Poll for changes via NOOP
                try:
                    typ, data = client.conn.noop()
                    if typ == "OK":
                        # Check for EXISTS/RECENT in untagged responses
                        response_text = str(data or [])
                        if "EXISTS" in response_text:
                            self._on_notification(
                                self.account_email, "INBOX", "exists",
                            )
                        if "FLAGS" in response_text:
                            self._on_notification(
                                self.account_email, "INBOX", "flags",
                            )
                except Exception:
                    break

        except Exception as exc:
            logger.warning("[idle] Connection error for %s: %s",
                           self.account_email, exc)
        finally:
            self._connected = False
            try:
                client.disconnect()
            except Exception:
                pass


class IMAPIdleManager:
    """Manage all per-account IDLE threads.

    Handles lifecycle: start, stop, status reporting.
    """

    def __init__(self):
        self._threads: dict[str, IMAPIdleThread] = {}
        self._lock = threading.Lock()

    def start_for_account(
        self,
        account_email: str,
        host: str, port: int, use_ssl: bool,
        username: str, password: str,
        on_notification: Callable[[str, str, str], None],
    ) -> bool:
        """Start an IDLE thread for an account.

        Args:
            account_email: Account to monitor.
            host: IMAP server host.
            port: IMAP server port.
            use_ssl: Whether to use SSL.
            username: IMAP username.
            password: IMAP password.
            on_notification: Callback for notifications.

        Returns:
            True if the thread was started, False if already running.
        """
        with self._lock:
            existing = self._threads.get(account_email)
            if existing and existing.is_alive:
                logger.debug("[idle] Already running for %s", account_email)
                return False

            thread = IMAPIdleThread(
                account_email=account_email,
                host=host, port=port, use_ssl=use_ssl,
                username=username, password=password,
                on_notification=on_notification,
            )
            self._threads[account_email] = thread

        thread.start()
        return True

    def stop_for_account(self, account_email: str) -> None:
        """Stop the IDLE thread for a specific account."""
        with self._lock:
            thread = self._threads.pop(account_email, None)
        if thread:
            thread.stop()

    def stop_all(self) -> None:
        """Stop all IDLE threads."""
        with self._lock:
            emails = list(self._threads.keys())
        for email in emails:
            self.stop_for_account(email)

    @property
    def active_accounts(self) -> list[str]:
        """List accounts with active IDLE threads."""
        with self._lock:
            return list(self._threads.keys())

    def status_all(self) -> list[dict[str, Any]]:
        """Get status dict for all IDLE threads."""
        results = []
        with self._lock:
            for email, thread in list(self._threads.items()):
                results.append(thread.status)
        return results


__all__ = ["IMAPIdleThread", "IMAPIdleManager"]
