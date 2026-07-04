"""Tests for email/smtp.py — SMTPClient, send_email."""
from __future__ import annotations

import smtplib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.email.smtp import SMTPClient


class TestSMTPClientInit:
    def test_init_defaults(self):
        client = SMTPClient("smtp.example.com")
        assert client.host == "smtp.example.com"
        assert client.port == 587
        assert client.use_tls is True
        assert client.use_ssl is False
        assert client._conn is None

    def test_init_ssl(self):
        client = SMTPClient("smtp.example.com", 465, use_ssl=True)
        assert client.use_ssl is True
        assert client.use_tls is True

    def test_init_plain(self):
        client = SMTPClient("smtp.example.com", 25, use_tls=False)
        assert client.use_tls is False
        assert client.use_ssl is False


class TestSMTPClientConnect:
    @patch("smtplib.SMTP")
    def test_connect_tls_success(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        client = SMTPClient("smtp.example.com", 587, use_tls=True)
        client.connect("user@example.com", "secret")
        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=30)
        mock_conn.ehlo.assert_called()
        mock_conn.starttls.assert_called_once()
        mock_conn.login.assert_called_once_with("user@example.com", "secret")

    @patch("smtplib.SMTP_SSL")
    def test_connect_ssl_success(self, mock_smtp_ssl):
        mock_conn = MagicMock()
        mock_smtp_ssl.return_value = mock_conn
        client = SMTPClient("smtp.example.com", 465, use_ssl=True)
        client.connect("user@example.com", "secret")
        mock_smtp_ssl.assert_called_once_with("smtp.example.com", 465, timeout=30)
        mock_conn.login.assert_called_once_with("user@example.com", "secret")

    @patch("smtplib.SMTP")
    def test_connect_no_tls(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        client = SMTPClient("smtp.example.com", 25, use_tls=False)
        client.connect("user", "pass")
        mock_conn.ehlo.assert_called_once()
        mock_conn.starttls.assert_not_called()
        mock_conn.login.assert_called_once()

    @patch("smtplib.SMTP")
    def test_connect_auth_failure(self, mock_smtp):
        mock_conn = MagicMock()
        mock_conn.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")
        mock_smtp.return_value = mock_conn
        client = SMTPClient("smtp.example.com")
        with pytest.raises(ConnectionError, match="SMTP authentication failed"):
            client.connect("user@example.com", "wrong")

    @patch("smtplib.SMTP", side_effect=TimeoutError("timed out"))
    def test_connect_timeout(self, mock_smtp):
        client = SMTPClient("smtp.example.com")
        with pytest.raises(ConnectionError, match="SMTP connection failed"):
            client.connect("user", "pass")


class TestSMTPClientConnProperty:
    def test_conn_raises_when_not_connected(self):
        client = SMTPClient("smtp.example.com")
        with pytest.raises(RuntimeError, match="Not connected"):
            _ = client.conn

    def test_conn_returns_when_connected(self):
        client = SMTPClient("smtp.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        assert client.conn is mock_conn


class TestSMTPClientDisconnect:
    def test_disconnect_connected(self):
        client = SMTPClient("smtp.example.com")
        mock_conn = MagicMock()
        client._conn = mock_conn
        client.disconnect()
        mock_conn.quit.assert_called_once()
        assert client._conn is None

    def test_disconnect_not_connected(self):
        client = SMTPClient("smtp.example.com")
        client.disconnect()  # Should not raise

    def test_disconnect_quit_raises(self):
        client = SMTPClient("smtp.example.com")
        mock_conn = MagicMock()
        mock_conn.quit.side_effect = Exception("quit failed")
        client._conn = mock_conn
        client.disconnect()  # Should not raise
        assert client._conn is None


class TestSMTPClientSendEmail:
    @patch("smtplib.SMTP")
    def test_send_simple_text(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        mock_conn.sendmail.return_value = {}

        client = SMTPClient("smtp.example.com")
        client._conn = mock_conn

        msg_id = client.send_email(
            from_addr="from@example.com",
            to=["to@example.com"],
            subject="Test",
            body="Hello World",
        )
        assert msg_id is not None
        mock_conn.sendmail.assert_called_once()

    @patch("smtplib.SMTP")
    def test_send_with_cc_and_bcc(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        mock_conn.sendmail.return_value = {}

        client = SMTPClient("smtp.example.com")
        client._conn = mock_conn

        msg_id = client.send_email(
            from_addr="from@example.com",
            to=["to@example.com"],
            cc=["cc@example.com"],
            bcc=["bcc@example.com"],
            subject="Test",
            body="Hello",
        )
        assert msg_id is not None
        # sendmail should be called with all recipients
        call_args = mock_conn.sendmail.call_args[0]
        assert len(call_args[1]) == 3  # to + cc + bcc

    @patch("smtplib.SMTP")
    def test_send_with_html(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        mock_conn.sendmail.return_value = {}

        client = SMTPClient("smtp.example.com")
        client._conn = mock_conn

        msg_id = client.send_email(
            from_addr="from@example.com",
            to=["to@example.com"],
            subject="HTML Test",
            body="Plain text",
            html_body="<p>HTML content</p>",
        )
        assert msg_id is not None
        # Should have called sendmail
        assert mock_conn.sendmail.called

    @patch("smtplib.SMTP")
    def test_send_with_signature(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        mock_conn.sendmail.return_value = {}

        client = SMTPClient("smtp.example.com")
        client._conn = mock_conn

        client.send_email(
            from_addr="from@example.com",
            to=["to@example.com"],
            subject="Sig Test",
            body="Body",
            signature="Sent from lighterbird",
        )
        # Should append signature (body is base64 encoded in MIME output)
        call_args = mock_conn.sendmail.call_args[0]
        msg_str = call_args[2]
        # The base64 encoding of "Body\n\n--\nSent from lighterbird" 
        assert "U2VudCBmcm9tIGxpZ2h0ZXJiaXJk" in msg_str

    @patch("smtplib.SMTP")
    def test_send_with_message_id(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        mock_conn.sendmail.return_value = {}

        client = SMTPClient("smtp.example.com")
        client._conn = mock_conn

        msg_id = client.send_email(
            from_addr="from@example.com",
            to=["to@example.com"],
            subject="ID Test",
            body="Body",
            message_id="custom-id@example.com",
        )
        assert msg_id == "custom-id@example.com"

    @patch("smtplib.SMTP")
    def test_send_with_in_reply_to(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        mock_conn.sendmail.return_value = {}

        client = SMTPClient("smtp.example.com")
        client._conn = mock_conn

        client.send_email(
            from_addr="from@example.com",
            to=["to@example.com"],
            subject="Re: Test",
            body="Reply",
            in_reply_to="orig-id@example.com",
        )
        call_args = mock_conn.sendmail.call_args[0]
        msg_str = call_args[2]
        assert "In-Reply-To" in msg_str
        assert "References" in msg_str

    @patch("smtplib.SMTP")
    def test_send_partial_failure(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        mock_conn.sendmail.return_value = {"bad@example.com": (550, "User unknown")}

        client = SMTPClient("smtp.example.com")
        client._conn = mock_conn

        with pytest.raises(ConnectionError, match="SMTP send partially failed"):
            client.send_email(
                from_addr="from@example.com",
                to=["to@example.com", "bad@example.com"],
                subject="Test",
                body="Hello",
            )

    @patch("smtplib.SMTP")
    def test_send_smtp_error(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        mock_conn.sendmail.side_effect = smtplib.SMTPException("Server unavailable")

        client = SMTPClient("smtp.example.com")
        client._conn = mock_conn

        with pytest.raises(ConnectionError, match="SMTP send failed"):
            client.send_email(
                from_addr="from@example.com",
                to=["to@example.com"],
                subject="Test",
                body="Hello",
            )


class TestSMTPClientAttachFile:
    @patch("smtplib.SMTP")
    def test_attach_file_dict(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        mock_conn.sendmail.return_value = {}

        import base64
        client = SMTPClient("smtp.example.com")
        client._conn = mock_conn

        client.send_email(
            from_addr="from@example.com",
            to=["to@example.com"],
            subject="Attach Test",
            body="See attached",
            attachments=[{"name": "test.txt", "data": base64.b64encode(b"hello").decode()}],
        )
        assert mock_conn.sendmail.called

    @patch("smtplib.SMTP")
    def test_attach_file_path_missing(self, mock_smtp):
        mock_conn = MagicMock()
        mock_smtp.return_value = mock_conn
        mock_conn.sendmail.return_value = {}

        client = SMTPClient("smtp.example.com")
        client._conn = mock_conn

        # Missing file should be skipped silently
        client.send_email(
            from_addr="from@example.com",
            to=["to@example.com"],
            subject="Missing Attach",
            body="Body",
            attachments=[Path("/nonexistent/file.txt")],
        )
        assert mock_conn.sendmail.called
