"""SMTP send engine for lighterbird.

Forked from A-lien's smtp.py. Supports plain text, HTML, attachments,
and optional signature footer.
"""

from __future__ import annotations

import smtplib
import socket
import ssl
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path
from typing import Any


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
            raise ConnectionError(
                f"SMTP authentication failed for {username}@{self.host}:{self.port} — {e}"
            ) from e
        except (socket.gaierror, ConnectionRefusedError,
                TimeoutError, socket.timeout, ssl.SSLError, OSError) as e:
            raise ConnectionError(
                f"SMTP connection failed to {username}@{self.host}:{self.port} — {e}"
            ) from e
        except Exception as e:
            raise ConnectionError(
                f"SMTP connection failed to {username}@{self.host}:{self.port} — {e}"
            ) from e

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
        bcc: list[str] | None = None,
        html_body: str = "",
        attachments: list[str | Path] | None = None,
        signature: str = "",
    ) -> None:
        """Send an email message with optional HTML, attachments, and signature.

        Args:
            from_addr: Sender email address.
            to: List of primary recipients.
            subject: Email subject.
            body: Plain text body.
            cc: Carbon copy recipients.
            bcc: Blind carbon copy recipients.
            html_body: Optional HTML body (alters MIME structure to
                ``multipart/alternative``).
            attachments: List of file paths to attach.
            signature: Optional signature appended to the plain text body.
        """
        cc = cc or []
        bcc = bcc or []
        attachments = attachments or []

        all_recipients = to + cc + bcc

        # Append signature to body
        full_body = body
        if signature and full_body:
            full_body += f"\n\n--\n{signature}"
        elif signature:
            full_body = signature

        has_attachments = bool(attachments)
        has_html = bool(html_body) or bool(attachments)
        use_multipart = has_attachments or (has_html and full_body)

        if use_multipart:
            # Determine the root multipart type
            if has_attachments:
                msg = MIMEMultipart("mixed")
            elif has_html and full_body:
                msg = MIMEMultipart("alternative")
            else:
                msg = MIMEMultipart()

            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = ", ".join(to)
            if cc:
                msg["Cc"] = ", ".join(cc)

            # If we have attachments, nest alternative inside mixed
            if has_attachments and (full_body or has_html):
                alt_part = MIMEMultipart("alternative")
                if full_body:
                    alt_part.attach(MIMEText(full_body, "plain", "utf-8"))
                if html_body:
                    alt_part.attach(MIMEText(html_body, "html", "utf-8"))
                msg.attach(alt_part)
            else:
                if full_body:
                    msg.attach(MIMEText(full_body, "plain", "utf-8"))
                if html_body:
                    msg.attach(MIMEText(html_body, "html", "utf-8"))

            for path in attachments:
                self._attach_file(msg, path)
        else:
            msg = MIMEText(full_body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = from_addr
            msg["To"] = ", ".join(to)
            if cc:
                msg["Cc"] = ", ".join(cc)

        try:
            failed = self.conn.sendmail(from_addr, all_recipients, msg.as_string())
            if failed:
                raise ConnectionError(
                    f"SMTP send partially failed: {', '.join(failed.keys())}"
                )
        except Exception as e:
            raise ConnectionError(f"SMTP send failed: {e}") from e

    @staticmethod
    def _attach_file(msg: MIMEMultipart, path: str | Path) -> None:
        """Attach a file to a MIME message."""
        path = Path(path)
        if not path.exists():
            return
        with path.open("rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{path.name}"',
            )
            msg.attach(part)
