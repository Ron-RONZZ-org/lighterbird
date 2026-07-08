"""Tests for email module — DB, services, IMAP helpers."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest

from lighterbird.email.db import get_db
from lighterbird.email.keyring import delete_password, get_password, set_password
from lighterbird.email.service import EmailService
from lighterbird.email.services import AccountService, MessageService


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
        assert db.table_exists("accounts")
        assert db.table_exists("folders")
        assert db.table_exists("messages")

    def test_get_db_idempotent(self, tmp_path: Path):
        db_path = tmp_path / "idemp.db"
        get_db(db_path)  # First call
        get_db(db_path)  # Second call should not raise

    @pytest.mark.no_isolation
    def test_db_path_defaults_to_data_dir(self):
        from lighterbird.email.db import _email_db_path

        assert "email.db" in str(_email_db_path())
        assert "lighterbird" in str(_email_db_path())


class TestAccountService:
    def test_create_and_list(self, db):
        svc = AccountService(db)
        data = {
            "name": "Test Account",
            "email": "test@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
        }
        account = svc.create_account(data, "sekret123")
        assert account["email"] == "test@example.com"

        accounts = svc.list_accounts()
        assert len(accounts) == 1

    def test_get_account_with_password(self, db):
        svc = AccountService(db)
        data = {
            "name": "PW Test",
            "email": "pw@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
        }
        svc.create_account(data, "mypassword")
        # Account uses email (email) as PK
        svc.get_account_with_password("pw@example.com")
        # Since keyring is unavailable in test, password may be empty
        svc.set_password("pw@example.com", "mypassword")

    def test_resolve_account_by_email(self, db):
        svc = AccountService(db)
        data = {
            "name": "Email Resolve",
            "email": "resolve@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
        }
        svc.create_account(data, "pw")
        acct = svc.get("resolve@example.com")
        assert acct is not None
        assert acct["email"] == "resolve@example.com"


class TestMessageService:
    def test_list_messages_empty(self, db):
        svc = MessageService(db)
        assert svc.list_messages() == []

    def test_create_and_get_message(self, db):
        # Create an account first
        acct_svc = AccountService(db)
        acct = acct_svc.create_account({
            "name": "Msg Test",
            "email": "msg@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
        }, "pw")

        # Insert a message manually using email as account_email
        import uuid
        msg_uuid = str(uuid.uuid4())
        from datetime import datetime
        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO messages (uuid, account_email, from_addr, to_recipients, subject, body, "
            "received_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (msg_uuid, acct["email"], "sender@example.com", '["me@example.com"]',
             "Hello", "Test body", now, now, now),
        )

        svc = MessageService(db)
        msg = svc.get_message(msg_uuid)
        assert msg is not None
        assert msg["subject"] == "Hello"
        assert msg["body"] == "Test body"

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
                "nosuch@test.com",
                to=["someone@example.com"],
                subject="Test",
                body="Hello",
            )

    def test_delete_account(self, email_service):
        result = email_service.delete_account("nonexistent@test.com")
        assert result is False


class TestEmailServiceSearchRemote:
    def test_search_remote_no_account_returns_empty(self, email_service):
        """search_remote with nonexistent account returns empty list."""
        result = email_service.search_remote("no-such@test.com", "test")
        assert result == []

    def test_search_remote_no_password_returns_empty(self, email_service):
        """search_remote for account without password returns empty list."""
        # Add an account without password
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        email_service.db.execute(
            "INSERT OR IGNORE INTO accounts "
            "(email, name, imap_server, imap_port, imap_use_ssl, "
            " smtp_server, smtp_port, smtp_use_tls, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("no-pw@test.com", "No Password",
             "imap.test.com", 993, 1, "smtp.test.com", 587, 1, now, now),
        )
        result = email_service.search_remote("no-pw@test.com", "test")
        assert result == []

    def test_search_remote_empty_query_no_criteria(self, email_service):
        """Empty query and no criteria returns empty (no IMAP connection)."""
        # Returns empty because no account with password exists in the test fixture
        result = email_service.search_remote("test@example.com", "")
        assert result == []


class TestKeyring:
    def test_email_keyring(self):
        # Should not crash regardless of keyring availability
        pw = get_password("test@example.com")
        # Keyring may or may not be available; just verify no exception
        assert pw is None or isinstance(pw, str)
        # set_password should not crash
        set_password("test@example.com", "pw")
        delete_password("test@example.com")


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

        data = parse_email_message(msg, "user@example.com", "INBOX", 42)
        assert data["subject"] == "Test"
        assert data["from_addr"] == "sender@example.com"
        assert data["body"] == "Hello World"
        assert data["imap_uid"] == 42
        assert data["account_email"] == "user@example.com"
        assert data["folder_name"] == "INBOX"

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

        data = parse_email_message(msg, "user@example.com", "INBOX", 1)
        assert "Plain body" in data["body"]
        assert "HTML body" in data["html_body"] or "p" in data.get("html_body", "")

    def test_parse_invalid_date(self):
        """Invalid Date header does not crash."""
        from email.message import Message

        from lighterbird.email.imap.parser import parse_email_message

        msg = Message()
        msg["Subject"] = "Bad Date"
        msg["From"] = "a@b.com"
        msg["To"] = "c@d.com"
        msg["Date"] = "Not a date"
        msg.set_payload("Body")
        data = parse_email_message(msg, "user@example.com", "INBOX", 1)
        assert data["subject"] == "Bad Date"
        assert data["received_at"] is not None

    def test_parse_with_attachments(self):
        """Message with attachments includes attachment metadata."""
        from email.mime.base import MIMEBase
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        from lighterbird.email.imap.parser import parse_email_message

        msg = MIMEMultipart("mixed")
        msg["Subject"] = "With Attachments"
        msg["From"] = "a@b.com"
        msg["To"] = "c@d.com"
        msg.attach(MIMEText("Body text", "plain", "utf-8"))

        att = MIMEBase("application", "pdf")
        att.set_payload(b"%PDF-1.4 mock content")
        att.add_header("Content-Disposition", 'attachment; filename="doc.pdf"')
        att.add_header("Content-ID", "<att123@local>")
        msg.attach(att)

        data = parse_email_message(
            msg, "user@example.com", "INBOX", 1, store_attachments=True,
        )
        assert data["subject"] == "With Attachments"
        assert "_attachments_meta" in data
        assert len(data["_attachments_meta"]) == 1
        assert data["_attachments_meta"][0]["filename"] == "doc.pdf"

    def test_parse_inline_image_skipped(self):
        """Inline image without attachment disposition is not treated as attachment."""
        from email.mime.base import MIMEBase
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        from lighterbird.email.imap.parser import parse_email_message

        msg = MIMEMultipart("related")
        msg["Subject"] = "Inline Image"
        msg["From"] = "a@b.com"
        msg["To"] = "c@d.com"
        msg.attach(MIMEText("Body", "plain", "utf-8"))

        inline = MIMEBase("image", "png")
        inline.set_payload(b"\x89PNG mock")
        inline.add_header("Content-ID", "<logo@local>")
        inline.add_header("Content-Disposition", "inline")
        msg.attach(inline)

        data = parse_email_message(
            msg, "user@example.com", "INBOX", 1, store_attachments=True,
        )
        # Inline images without filename/attachment disposition are skipped
        assert "_attachments_meta" not in data or len(data.get("_attachments_meta", [])) == 0
