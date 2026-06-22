"""SMTP send engine for lighterbird.

Forked from A-lien's smtp.py, simplified for MVP (plain text only, no attachments).
"""

from __future__ import annotations

import smtplib
import socket
import ssl
from email.mime.text import MIMEText


class SMTPClient:
    """Low-level SMTP operations for sending email."""

    def __init__(self, host: str, port: int = 587, use_tls: bool = True, use_ssl: bool = False):
        self.host = host
        self.port = port
        self.use_tls = use_tls
        self.use_ssl = use_ssl
        self._conn: smtplib.SMTP | smtplib.SMTP_SSL | None = None

    def connect(self, username: str, password: str) -> None:
        """Connect, optionally upgrade to TLS, and login."""
        try:
            if self.use_ssl:
                self._conn = smtplib.SMTP_SSL(self.host, self.port, timeout=30)
            else:
                self._conn = smtplib.SMTP(self.host, self.port, timeout=30)
                self._conn.ehlo()
            if self.use_tls:
                self._conn.starttls()
                self._conn.ehlo()
            self._conn.login(username, password)
        except smtplib.SMTPAuthenticationError as e:
            raise ConnectionError(f"SMTP authentication failed for {username}@{self.host}:{self.port} — {e}") from e
        except (socket.gaierror, ConnectionRefusedError,
                TimeoutError, socket.timeout, ssl.SSLError, OSError) as e:
            raise ConnectionError(f"SMTP connection failed to {username}@{self.host}:{self.port} — {e}") from e
        except Exception as e:
            raise ConnectionError(f"SMTP connection failed to {username}@{self.host}:{self.port} — {e}") from e

    @property
    def conn(self) -> smtplib.SMTP | smtplib.SMTP_SSL:
        if self._conn is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._conn

    def disconnect(self) -> None:
        if self._conn:
            try:
                self._conn.quit()
            except Exception:
                pass
            self._conn = None

    def send_email(
        self,
        from_addr: str,
        to: list[str],
        subject: str,
        body: str = "",
        cc: list[str] | None = None,
    ) -> None:
        """Send a plain text email."""
        cc = cc or []
        all_recipients = to + cc

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)

        try:
            failed = self.conn.sendmail(from_addr, all_recipients, msg.as_string())
            if failed:
                raise ConnectionError(f"SMTP send partially failed: {', '.join(failed.keys())}")
        except Exception as e:
            raise ConnectionError(f"SMTP send failed: {e}") from e
