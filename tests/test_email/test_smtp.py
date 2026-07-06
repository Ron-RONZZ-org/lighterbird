"""Tests for email/smtp.py — SMTPClient with mocked smtplib."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from lighterbird.email.smtp import SMTPClient


@pytest.fixture
def mock_smtplib():
    with patch("lighterbird.email.smtp.smtplib") as mock:
        # Attach real exception classes so isinstance checks work
        import smtplib as _real_smtplib

        mock.SMTPAuthenticationError = _real_smtplib.SMTPAuthenticationError
        yield mock


# Note: socket and ssl are NOT mocked globally because the real exception
# classes (ConnectionRefusedError, ssl.SSLError, etc.) must be used in
# except clauses within smtp.py.  We only mock smtplib.SMTP below.


class TestSMTPClientInit:
    def test_default_port(self):
        client = SMTPClient("smtp.example.com")
        assert client.port == 587
        assert client.use_tls is True
        assert client.use_ssl is False

    def test_ssl_port_465(self):
        client = SMTPClient("smtp.example.com", port=465, use_ssl=True)
        assert client.use_ssl is True

    def test_no_tls(self):
        client = SMTPClient("smtp.example.com", use_tls=False)
        assert client.use_tls is False


class TestSMTPClientConnect:
    def test_connect_standard(self, mock_smtplib):
        client = SMTPClient("smtp.example.com", 587, use_tls=True)
        instance = MagicMock()
        mock_smtplib.SMTP.return_value = instance

        client.connect("user", "pass")
        mock_smtplib.SMTP.assert_called_once_with(
            "smtp.example.com", 587, timeout=30
        )
        instance.ehlo.assert_called()
        instance.starttls.assert_called_once()
        instance.login.assert_called_once_with("user", "pass")

    def test_connect_ssl(self, mock_smtplib):
        client = SMTPClient("smtp.example.com", 465, use_tls=False, use_ssl=True)
        instance = MagicMock()
        mock_smtplib.SMTP_SSL.return_value = instance

        client.connect("user", "pass")
        mock_smtplib.SMTP_SSL.assert_called_once_with(
            "smtp.example.com", 465, timeout=30
        )
        instance.login.assert_called_once_with("user", "pass")

    def test_connect_tls_without_starttls(self, mock_smtplib):
        """When use_tls is False, don't call starttls."""
        client = SMTPClient("smtp.example.com", 587, use_tls=False)
        instance = MagicMock()
        mock_smtplib.SMTP.return_value = instance

        client.connect("user", "pass")
        instance.starttls.assert_not_called()

    def test_connect_auth_error(self, mock_smtplib):
        client = SMTPClient("smtp.example.com")
        instance = MagicMock()
        instance.login.side_effect = mock_smtplib.SMTPAuthenticationError(
            535, b"Authentication failed"
        )
        mock_smtplib.SMTP.return_value = instance

        with pytest.raises(ConnectionError, match="SMTP authentication failed"):
            client.connect("user", "wrong")

    def test_connect_network_error(self, mock_smtplib):
        import socket

        client = SMTPClient("smtp.example.com")
        mock_smtplib.SMTP.side_effect = socket.gaierror("Name or service not known")

        with pytest.raises(ConnectionError, match="SMTP connection failed"):
            client.connect("user", "pass")

    def test_connect_generic_error(self, mock_smtplib):
        client = SMTPClient("smtp.example.com")
        mock_smtplib.SMTP.side_effect = RuntimeError("Unexpected error")

        with pytest.raises(ConnectionError, match="SMTP connection failed"):
            client.connect("user", "pass")


class TestSMTPClientConnProperty:
    def test_not_connected_raises(self):
        client = SMTPClient("smtp.example.com")
        with pytest.raises(RuntimeError, match="Not connected"):
            _ = client.conn

    def test_returns_connection(self, mock_smtplib):
        client = SMTPClient("smtp.example.com")
        instance = MagicMock()
        mock_smtplib.SMTP.return_value = instance
        client.connect("user", "pass")
        assert client.conn is instance


class TestSMTPClientDisconnect:
    def test_disconnect(self, mock_smtplib):
        client = SMTPClient("smtp.example.com")
        instance = MagicMock()
        mock_smtplib.SMTP.return_value = instance
        client.connect("user", "pass")
        client.disconnect()
        instance.quit.assert_called_once()
        assert client._conn is None

    def test_disconnect_no_connection(self):
        client = SMTPClient("smtp.example.com")
        client.disconnect()  # should not raise

    def test_disconnect_quit_error(self, mock_smtplib):
        client = SMTPClient("smtp.example.com")
        instance = MagicMock()
        instance.quit.side_effect = OSError("Connection reset")
        mock_smtplib.SMTP.return_value = instance
        client.connect("user", "pass")
        client.disconnect()  # should not raise


class TestSMTPClientSendEmail:
    @pytest.fixture
    def connected(self, mock_smtplib):
        client = SMTPClient("smtp.example.com")
        instance = MagicMock()
        instance.sendmail.return_value = {}  # empty = all delivered
        mock_smtplib.SMTP.return_value = instance
        client.connect("user", "pass")
        return client

    def test_send_plain_text(self, connected):
        msg_id = connected.send_email(
            from_addr="alice@example.com",
            to=["bob@example.com"],
            subject="Hello",
            body="World",
        )
        assert msg_id is not None
        connected.conn.sendmail.assert_called_once()

    def test_send_with_cc(self, connected):
        msg_id = connected.send_email(
            from_addr="alice@example.com",
            to=["bob@example.com"],
            subject="CC Test",
            body="Body",
            cc=["cc@example.com"],
        )
        assert msg_id is not None
        # Verify CC is in the message
        call_args = connected.conn.sendmail.call_args
        msg_str = call_args[0][2]
        assert "Cc: cc@example.com" in msg_str

    def test_send_with_bcc(self, connected):
        """BCC recipients receive the email but are not in headers."""
        msg_id = connected.send_email(
            from_addr="alice@example.com",
            to=["bob@example.com"],
            subject="BCC Test",
            body="Body",
            bcc=["bcc@example.com"],
        )
        assert msg_id is not None
        call_args = connected.conn.sendmail.call_args
        recipients = call_args[0][1]
        # BCC should be in the envelope
        assert "bcc@example.com" in recipients

    def _decode_body(self, msg_str):
        """Decode a base64-encoded email body to plain text."""
        import base64
        import re

        # Extract the base64 payload between headers and the end
        match = re.search(
            r"\n\n([A-Za-z0-9+/=]+)\n?$", msg_str.replace("\r\n", "\n")
        )
        if match:
            try:
                return base64.b64decode(match.group(1)).decode("utf-8")
            except Exception:
                pass
        return msg_str

    def test_send_with_in_reply_to(self, connected):
        msg_id = connected.send_email(
            from_addr="alice@example.com",
            to=["bob@example.com"],
            subject="Re: Original",
            body="Reply",
            in_reply_to="<original@mail.com>",
        )
        call_args = connected.conn.sendmail.call_args
        msg_str = call_args[0][2]
        # Note: in_reply_to value gets wrapped in angle brackets by smtp.py
        assert "In-Reply-To: " in msg_str
        assert "References: " in msg_str

    def test_send_with_html_body(self, connected):
        msg_id = connected.send_email(
            from_addr="alice@example.com",
            to=["bob@example.com"],
            subject="HTML Test",
            body="Text version",
            html_body="<p>HTML version</p>",
        )
        assert msg_id is not None
        call_args = connected.conn.sendmail.call_args
        msg_str = call_args[0][2]
        # In multipart/alternative, the HTML part has text/html content type
        assert "multipart/alternative" in msg_str

    def test_send_with_attachment_dict(self, connected):
        msg_id = connected.send_email(
            from_addr="alice@example.com",
            to=["bob@example.com"],
            subject="Attachment Test",
            body="See attached",
            attachments=[{"name": "file.txt", "data": "aGVsbG8="}],
        )
        assert msg_id is not None
        call_args = connected.conn.sendmail.call_args
        msg_str = call_args[0][2]
        assert "file.txt" in msg_str
        assert "application/octet-stream" in msg_str

    def test_send_with_custom_message_id(self, connected):
        msg_id = connected.send_email(
            from_addr="alice@example.com",
            to=["bob@example.com"],
            subject="Custom ID",
            body="Body",
            message_id="custom-id@example.com",
        )
        assert msg_id == "custom-id@example.com"
        call_args = connected.conn.sendmail.call_args
        msg_str = call_args[0][2]
        assert "Message-ID: <custom-id@example.com>" in msg_str

    def test_send_with_signature(self, connected):
        msg_id = connected.send_email(
            from_addr="alice@example.com",
            to=["bob@example.com"],
            subject="Sig Test",
            body="Hello",
            signature="John Smith",
        )
        assert msg_id is not None
        call_args = connected.conn.sendmail.call_args
        msg_str = call_args[0][2]
        body = self._decode_body(msg_str)
        assert "John Smith" in body

    def test_send_signature_without_body(self, connected):
        """Signature alone becomes the body."""
        msg_id = connected.send_email(
            from_addr="alice@example.com",
            to=["bob@example.com"],
            subject="Sig Only",
            signature="Just a signature",
        )
        assert msg_id is not None
        call_args = connected.conn.sendmail.call_args
        msg_str = call_args[0][2]
        body = self._decode_body(msg_str)
        assert "Just a signature" in body

    def test_send_partial_failure(self, connected):
        connected.conn.sendmail.return_value = {"bob@example.com": (550, "User unknown")}
        with pytest.raises(ConnectionError, match="SMTP send partially failed"):
            connected.send_email(
                from_addr="alice@example.com",
                to=["bob@example.com"],
                subject="Partial Fail",
                body="Test",
            )

    def test_send_generic_failure(self, connected):
        connected.conn.sendmail.side_effect = RuntimeError("Server busy")
        with pytest.raises(ConnectionError, match="SMTP send failed"):
            connected.send_email(
                from_addr="alice@example.com",
                to=["bob@example.com"],
                subject="Fail",
                body="Test",
            )


class TestSMTPClientAttachFile:
    def test_attach_dict_with_b64_data(self):
        """Dict attachment with base64 data."""
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()
        SMTPClient._attach_file(msg, {"name": "doc.pdf", "data": "dGVzdA=="})
        # Should not raise, attachment should be added
        assert len(msg.get_payload()) == 1

    def test_attach_dict_with_text_data(self):
        """Dict attachment with plain string data (not b64)."""
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()
        SMTPClient._attach_file(msg, {"name": "note.txt", "data": "hello"})
        assert len(msg.get_payload()) == 1

    def test_attach_file_path(self, tmp_path):
        """File path attachment from disk."""
        from email.mime.multipart import MIMEMultipart

        test_file = tmp_path / "test.txt"
        test_file.write_text("file content")
        msg = MIMEMultipart()
        SMTPClient._attach_file(msg, str(test_file))
        assert len(msg.get_payload()) == 1

    def test_attach_nonexistent_path(self, tmp_path):
        """Non-existent file path is silently skipped."""
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()
        SMTPClient._attach_file(msg, str(tmp_path / "nonexistent.txt"))
        assert len(msg.get_payload()) == 0

    def test_attach_dict_with_bytes_data(self):
        """Dict attachment with bytes data."""
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart()
        SMTPClient._attach_file(msg, {"name": "data.bin", "data": b"binary"})
        assert len(msg.get_payload()) == 1
