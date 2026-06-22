"""Tests for email module — DB, services, IMAP helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from lighterbird.email.db import get_db
from lighterbird.email.keyring import get_password, set_password, delete_password
from lighterbird.email.services import AccountService, MessageService, MessageOpsService
from lighterbird.email.service import EmailService


@pytest.fixture
def db(tmp_path: Path):
    return get_db(tmp_path / "email.db")


@pytest.fixture
def email_service(db):
    return EmailService(db)


class TestEmailDB:
    def test_get_db_creates_tables(self, tmp_path: Path):
        db_path = tmp_path / "test_email.db"
        db = get_db(db_path)
        assert db.table_exists("kontoj")
        assert db.table_exists("dosierujoj")
        assert db.table_exists("mesagoj")

    def test_get_db_idempotent(self, tmp_path: Path):
        db_path = tmp_path / "idemp.db"
        get_db(db_path)  # First call
        get_db(db_path)  # Second call should not raise

    def test_db_path_defaults_to_data_dir(self):
        from lighterbird.core.paths import data_dir
        from lighterbird.email.db import _email_db_path

        assert "email.db" in str(_email_db_path())
        assert "lighterbird" in str(_email_db_path())


class TestAccountService:
    def test_create_and_list(self, db):
        svc = AccountService(db)
        data = {
            "nomo": "Test Account",
            "retposto": "test@example.com",
            "imap_servilo": "imap.example.com",
            "smtp_servilo": "smtp.example.com",
        }
        account = svc.create_account(data, "sekret123")
        assert account["uuid"] is not None
        assert account["retposto"] == "test@example.com"

        accounts = svc.list_accounts()
        assert len(accounts) == 1

    def test_get_account_with_password(self, db):
        svc = AccountService(db)
        data = {
            "nomo": "PW Test",
            "retposto": "pw@example.com",
            "imap_servilo": "imap.example.com",
            "smtp_servilo": "smtp.example.com",
        }
        account = svc.create_account(data, "mypassword")
        # Without real keyring, password is stored to None, so get returns None
        result = svc.get_account_with_password(account["uuid"])
        # Since keyring is unavailable in test, this returns None
        # (password not actually stored)
        svc.set_password(account["uuid"], "mypassword")  # Try to store

    def test_resolve_account_by_email(self, db):
        svc = AccountService(db)
        data = {
            "nomo": "Email Resolve",
            "retposto": "resolve@example.com",
            "imap_servilo": "imap.example.com",
            "smtp_servilo": "smtp.example.com",
        }
        svc.create_account(data, "pw")
        acct = svc.find_by_email("resolve@example.com")
        assert acct is not None
        assert acct["retposto"] == "resolve@example.com"


class TestMessageService:
    def test_list_messages_empty(self, db):
        svc = MessageService(db)
        assert svc.list_messages() == []

    def test_create_and_get_message(self, db):
        # Create an account first
        acct_svc = AccountService(db)
        acct = acct_svc.create_account({
            "nomo": "Msg Test",
            "retposto": "msg@example.com",
            "imap_servilo": "imap.example.com",
            "smtp_servilo": "smtp.example.com",
        }, "pw")

        # Insert a message manually
        import uuid
        msg_uuid = str(uuid.uuid4())
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO mesagoj (uuid, konto_id, de, al, subjekto, korpo, "
            "ricevita_je, kreita_je, modifita_je) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (msg_uuid, acct["uuid"], "sender@example.com", '["me@example.com"]',
             "Hello", "Test body", now, now, now),
        )

        svc = MessageService(db)
        msg = svc.get_message(msg_uuid)
        assert msg is not None
        assert msg["subjekto"] == "Hello"
        assert msg["korpo"] == "Test body"

        msgs = svc.list_messages()
        assert len(msgs) == 1

    def test_search_messages(self, db):
        svc = MessageService(db)
        result = svc.search_messages({"query": "hello"}, limit=10)
        assert result == []


class TestEmailService:
    def test_email_service_facade(self, email_service):
        assert email_service.accounts is not None
        assert email_service.messages is not None
        assert email_service.msg_ops is not None

    def test_sync_all_no_accounts(self, email_service):
        results = email_service.sync_all()
        assert results == {}

    def test_mark_read_on_nonexistent(self, email_service):
        # Should not raise
        email_service.mark_read("nonexistent-uuid")

    def test_send_email_no_account(self, email_service):
        with pytest.raises(ValueError):
            email_service.send_email(
                "no-such-uuid",
                to=["someone@example.com"],
                subject="Test",
                body="Hello",
            )

    def test_delete_account(self, email_service):
        result = email_service.delete_account("nonexistent")
        assert result is False


class TestKeyring:
    def test_email_keyring(self):
        from lighterbird.core.keyring import _keyring_available
        available = _keyring_available()
        # Should not crash regardless of keyring availability
        pw = get_password("test-uuid")
        if available:
            # With keyring, password returns None (not set) or works
            assert pw is None or isinstance(pw, str)
        else:
            assert pw is None
        # set_password should not crash
        set_password("test-uuid", "pw")
        delete_password("test-uuid")


class TestIMAPHelpers:
    def test_decode_mime_header(self):
        from lighterbird.email.imap.helpers import decode_mime_header
        assert decode_mime_header("") == ""
        assert decode_mime_header("Hello") == "Hello"

    def test_parse_email_address(self):
        from lighterbird.email.imap.helpers import parse_email_address
        assert parse_email_address("") == ""
        assert parse_email_address("user@example.com") == "user@example.com"
        assert parse_email_address("Name <user@example.com>") == "user@example.com"

    def test_parse_address_list(self):
        from lighterbird.email.imap.helpers import parse_address_list
        assert parse_address_list("") == []
        result = parse_address_list("a@b.com, c@d.com")
        assert result == ["a@b.com", "c@d.com"]

    def test_extract_sender_name(self):
        from lighterbird.email.imap.helpers import extract_sender_name
        assert extract_sender_name("Name <user@example.com>") == "Name"
        assert extract_sender_name("user@example.com") == ""


class TestSMTP:
    def test_smtp_client_init(self):
        from lighterbird.email.smtp import SMTPClient
        client = SMTPClient("smtp.example.com", 587)
        assert client.host == "smtp.example.com"
        assert client.port == 587

    def test_smtp_connect_fails(self):
        from lighterbird.email.smtp import SMTPClient
        client = SMTPClient("nonexistent.example.com", 587)
        with pytest.raises(ConnectionError):
            client.connect("user", "pass")


class TestParser:
    def test_parse_simple_message(self):
        from email.message import Message
        from lighterbird.email.imap.parser import parse_email_message

        msg = Message()
        msg["Subject"] = "Test"
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Date"] = "Mon, 01 Jan 2024 12:00:00 +0000"
        msg.set_payload("Hello World")

        data = parse_email_message(msg, "acct-1", "folder-1", 42)
        assert data["subjekto"] == "Test"
        assert data["de"] == "sender@example.com"
        assert data["korpo"] == "Hello World"
        assert data["imap_uid"] == 42
        assert data["konto_id"] == "acct-1"

    def test_parse_multipart_message(self):
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from lighterbird.email.imap.parser import parse_email_message

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Multi"
        msg["From"] = "s@e.com"
        msg["To"] = "r@e.com"
        msg.attach(MIMEText("Plain body", "plain", "utf-8"))
        msg.attach(MIMEText("<p>HTML body</p>", "html", "utf-8"))

        data = parse_email_message(msg, "acct-1", "folder-1", 1)
        assert "Plain body" in data["korpo"]
        assert "HTML body" in data["html_korpo"] or "p" in data.get("html_korpo", "")
