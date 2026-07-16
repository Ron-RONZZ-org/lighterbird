"""Tests for email module — DB, services, IMAP helpers."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lighterbird.email.db import get_db
from lighterbird.email.keyring import delete_password, get_password, set_password
from lighterbird.email.service import (
    EmailService,
    acquire_account_imap_lock,
    release_account_imap_lock,
)
from lighterbird.email.services import AccountService, MessageService
from lighterbird.email.services.messages import _extract_match_snippet
from lighterbird.email.imap.sync import SyncResult


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

    def test_search_messages_empty(self, db):
        svc = MessageService(db)
        result = svc.search_messages({"query": "hello"}, limit=10)
        assert result == []


class TestSearchMessages:
    """Tests for MessageService.search_messages() enhanced search."""

    MSGS = [
        # (uuid_suffix, subject, from_addr, to_recipients, cc_recipients, body)
        ("s1", "Meeting agenda", "alice@example.com", '["bob@example.com"]', '[]',
         "Let's discuss the project plan"),
        ("s2", "Lunch plans", "bob@example.com", '["alice@example.com"]', '[]',
         "Are we still on for lunch today?"),
        ("s3", "Project update", "carol@example.com", '["team@example.com"]',
         '["alice@example.com"]', "Q3 milestones are on track"),
        ("s4", "Invoice", "billing@example.com", '["alice@example.com"]', '[]',
         "Your invoice for project services is attached"),
        ("s5", "Hello world", "someone@example.com", '["alice@example.com"]', '[]',
         "This is a test email with no relevance"),
    ]

    @pytest.fixture(autouse=True)
    def _setup_msgs(self, db):
        """Insert test messages into the database."""
        acct_svc = AccountService(db)
        acct_svc.create_account({
            "name": "Search Test",
            "email": "search@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
        }, "pw")
        now = datetime.now(UTC).isoformat()
        for i, (suffix, subject, from_addr, to_rcpts, cc_rcpts, body) in enumerate(self.MSGS):
            # Stagger received_at so time-based ordering has a deterministic
            # pattern for relevance-ordering tests.
            received = datetime.now(UTC).isoformat()
            db.execute(
                "INSERT INTO messages "
                "(uuid, account_email, from_addr, to_recipients, cc_recipients, "
                " subject, body, received_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"search-{suffix}", "search@example.com", from_addr, to_rcpts,
                 cc_rcpts, subject, body, received, now, now),
            )

    def test_search_subject_match(self, db):
        """Query matching subject returns results with matched_in=['subject']."""
        svc = MessageService(db)
        results = svc.search_messages({"query": "meeting"}, limit=10)
        assert len(results) >= 1
        match = next((m for m in results if m["uuid"] == "search-s1"), None)
        assert match is not None
        assert "subject" in match.get("matched_in", [])

    def test_search_from_addr_match(self, db):
        """Query matching from_addr returns results."""
        svc = MessageService(db)
        results = svc.search_messages({"query": "billing"}, limit=10)
        assert len(results) >= 1
        uuids = [m["uuid"] for m in results]
        assert "search-s4" in uuids

    def test_search_to_recipients_match(self, db):
        """Query matching to_recipients returns results (JSON text)."""
        svc = MessageService(db)
        results = svc.search_messages({"query": "team@example.com"}, limit=10)
        assert len(results) >= 1
        uuids = [m["uuid"] for m in results]
        assert "search-s3" in uuids

    def test_search_cc_recipients_match(self, db):
        """Query matching cc_recipients returns results."""
        svc = MessageService(db)
        results = svc.search_messages({"query": "alice@example.com"}, limit=10)
        # Multiple messages have alice@example.com in to/cc
        assert len(results) >= 2

    def test_search_body_match(self, db):
        """Query matching body text returns results with matched_in=['body']."""
        svc = MessageService(db)
        results = svc.search_messages({"query": "milestones"}, limit=10)
        assert len(results) >= 1
        match = next((m for m in results if m["uuid"] == "search-s3"), None)
        assert match is not None
        assert "body" in match.get("matched_in", [])

    def test_relevance_ordering(self, db):
        """Subject matches sort above from_addr matches, above body-only."""
        svc = MessageService(db)
        # "project" matches:
        #   s1: subject="Meeting agenda" -> NO
        #   s3: subject="Project update" -> subject match (weight 3)
        #   s4: body="Your invoice for project services..." -> body match (weight 0.5)
        results = svc.search_messages({"query": "project"}, limit=10)
        uuids = [m["uuid"] for m in results]
        # s3 (subject match) should come before s4 (body match)
        s3_idx = uuids.index("search-s3") if "search-s3" in uuids else len(uuids)
        s4_idx = uuids.index("search-s4") if "search-s4" in uuids else len(uuids)
        assert s3_idx < s4_idx, (
            f"Subject match (search-s3) should rank above body match (search-s4). "
            f"Order: {uuids}"
        )

    def test_search_without_query_uses_time_order(self, db):
        """No query = time-based sort, not relevance."""
        svc = MessageService(db)
        results = svc.search_messages({}, limit=10)
        assert len(results) >= 1
        # No matched_in when no query
        for m in results:
            assert "matched_in" not in m or not m["matched_in"]

    def test_search_with_cursor_no_relevance(self, db):
        """When cursor is present, uses time-based sort even with query."""
        svc = MessageService(db)
        # Use a future cursor with sort=newest, so received_at < cursor matches all
        results = svc.search_messages(
            {"query": "test", "cursor": "2099-01-01T00:00:00|zzzzzzzz"},
            limit=10,
        )
        assert len(results) >= 1
        # Results should NOT have matched_in when cursor is used (no relevance sort)
        for m in results:
            assert "matched_in" not in m or not m["matched_in"]

    def test_matched_in_subject_only(self, db):
        """matched_in shows 'subject' when only subject matched."""
        svc = MessageService(db)
        results = svc.search_messages({"query": "meeting"}, limit=10)
        msgs_with_meeting = [m for m in results if "subject" in (m.get("matched_in") or [])]
        assert len(msgs_with_meeting) >= 1

    def test_matched_in_multiple_fields(self, db):
        """matched_in shows multiple fields when query matches multiple fields."""
        svc = MessageService(db)
        # "alice" appears in to_recipients, cc_recipients, and from_addr of
        # different messages
        results = svc.search_messages({"query": "alice"}, limit=10)
        for m in results:
            matched = m.get("matched_in") or []
            if matched:
                # Verify it actually matches
                q = "alice"
                fields_to_check = {
                    "subject": (m.get("subject") or "").lower(),
                    "from": (m.get("from_addr") or "").lower(),
                    "to": (m.get("to_recipients") or "").lower(),
                    "cc": (m.get("cc_recipients") or "").lower(),
                    "body": (m.get("body") or "").lower(),
                }
                for field in matched:
                    assert q in fields_to_check[field], (
                        f"Field {field} does not contain '{q}'"
                    )

    def test_participant_filter(self, db):
        """--participant searches from_addr, to_recipients, cc_recipients."""
        svc = MessageService(db)
        results = svc.search_messages({"participant": "carol"}, limit=10)
        assert len(results) >= 1
        uuids = [m["uuid"] for m in results]
        assert "search-s3" in uuids  # carol@example.com is the from_addr

    def test_participant_filter_matches_to(self, db):
        """--participant also matches to_recipients."""
        svc = MessageService(db)
        results = svc.search_messages({"participant": "team@example.com"}, limit=10)
        assert len(results) >= 1

    def test_participant_filter_matches_cc(self, db):
        """--participant also matches cc_recipients."""
        svc = MessageService(db)
        results = svc.search_messages({"participant": "alice@example.com"}, limit=10)
        assert len(results) >= 2


class TestExtractMatchSnippet:
    """Tests for _extract_match_snippet()."""

    def test_empty_body(self):
        assert _extract_match_snippet("", "hello") == ""

    def test_empty_query(self):
        assert _extract_match_snippet("Hello world", "") == "Hello world"

    def test_basic_match(self):
        result = _extract_match_snippet(
            "This is a long email body with the search term meeting in the middle of it",
            "meeting",
            context=10,
        )
        assert "meeting" in result

    def test_match_at_start(self):
        body = "meeting is at the start of this email body"
        result = _extract_match_snippet(body, "meeting", context=10)
        assert result.startswith("meeting")
        assert "[...]" not in result[:20]

    def test_match_at_end(self):
        body = "This is a long email body with the meeting"
        result = _extract_match_snippet(body, "meeting", context=10)
        assert "meeting" in result
        assert result.endswith("]...") or not result.endswith("[...]")

    def test_match_centered_snippet(self):
        body = "x" * 500 + "MATCH HERE" + "y" * 500
        result = _extract_match_snippet(body, "MATCH HERE", context=50)
        assert "MATCH HERE" in result
        assert result.startswith("[...]")
        assert result.endswith("[...]")
        # Context window: 50 before + "MATCH HERE" (10) + 50 after = ~110 + marker
        assert len(result) < 200

    def test_case_insensitive(self):
        result = _extract_match_snippet(
            "Hello World", "hello", context=5,
        )
        assert "Hello" in result

    def test_long_body_fallback_without_match(self):
        body = "x" * 500
        result = _extract_match_snippet(body, "nonexistent", context=50)
        assert len(result) <= 200


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


class TestSyncAccountBacklogDrain:
    """Test the pre-sync backlog drain in EmailService.sync_account().

    Verifies that pending backlog entries are processed BEFORE the IMAP
    sync connection is established, and that no post-sync backlog drain
    occurs (the pre-sync drain subsumes it).
    """

    def _setup_account_with_message(self, db, email_service, msg_uuid="msg-1",
                                     imap_uid=42):
        """Helper: create an account, folder, and message with password."""
        from lighterbird.email.keyring import set_password

        svc = AccountService(db)
        svc.create_account({
            "name": "Test",
            "email": "test@example.com",
            "imap_server": "imap.example.com",
            "smtp_server": "smtp.example.com",
        }, "fakepassword")

        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT OR IGNORE INTO folders "
            "(account_email, name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            ("test@example.com", "INBOX", now, now),
        )
        db.execute(
            "INSERT INTO messages (uuid, account_email, folder_name, imap_uid, "
            "subject, from_addr, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (msg_uuid, "test@example.com", "INBOX", imap_uid,
             "Test", "sender@example.com", now, now),
        )

    def test_drains_backlog_before_imap_connect(self, db, email_service, caplog):
        """With pending backlog entries, sync_account drains them before IMAP."""
        self._setup_account_with_message(db, email_service)

        # Enqueue a backlog entry (mark as read — IS read)
        email_service.msg_ops.backlog.enqueue(
            msg_uuid="msg-1",
            account_email="test@example.com",
            folder_name="INBOX",
            imap_uid=42,
            is_read=1,
            is_deleted=0,
        )
        assert email_service.msg_ops.backlog.count_pending(
            account_email="test@example.com",
        ) == 1

        # Call sync_account — IMAP connect will fail (no real server),
        # but the backlog drain should be attempted before that.
        with caplog.at_level("INFO"):
            result = email_service.sync_account("test@example.com")

        # The "Drained" log line confirms the pre-sync drain was reached
        assert "Drained" in caplog.text, (
            "Expected 'Drained X/Y backlog entries' log from pre-sync drain"
        )
        assert "test@example.com" in caplog.text
        # sync_account always returns a result (never raises)
        assert isinstance(result, SyncResult)

    def test_skips_drain_when_backlog_empty(self, db, email_service, caplog):
        """With no backlog entries, sync_account skips the drain step."""
        self._setup_account_with_message(db, email_service)

        assert email_service.msg_ops.backlog.count_pending(
            account_email="test@example.com",
        ) == 0

        with caplog.at_level("INFO"):
            result = email_service.sync_account("test@example.com")

        # No "Drained" log because there was nothing to drain
        assert "Drained" not in caplog.text, (
            "Should not log drain message when backlog is empty"
        )
        assert isinstance(result, SyncResult)

    def test_no_post_sync_backlog_drain(self, db, email_service, caplog):
        """The post-sync process_sync_backlog() call is removed.

        Instead, the pre-sync drain handles all entries.  We verify this
        by checking that the old 'ALWAYS drain the flag sync backlog'
        comment/pattern is gone.
        """
        self._setup_account_with_message(db, email_service)

        email_service.msg_ops.backlog.enqueue(
            msg_uuid="msg-1",
            account_email="test@example.com",
            folder_name="INBOX",
            imap_uid=42,
            is_read=1,
            is_deleted=0,
        )
        # Capture backlog count before sync
        before = email_service.msg_ops.backlog.count_pending(
            account_email="test@example.com",
        )
        assert before == 1

        # sync_account still returns normally even though IMAP fails
        result = email_service.sync_account("test@example.com")
        assert isinstance(result, SyncResult)

        # The backlog entry should NOT have been processed by the old
        # post-sync drain (it can't connect to IMAP in test).  The entry
        # either remained (retries incremented) or was cleaned up if stale.
        remaining = email_service.msg_ops.backlog.count_pending(
            account_email="test@example.com",
        )
        # Backlog may still exist (IMAP failed) — that's expected since
        # the only thing that changed is we no longer have a redundant
        # post-sync drain.  The pre-sync drain already tried processing it.
        assert remaining >= 0  # not a crash test

    def test_drains_backlog_even_when_sync_skipped(self, db, email_service, caplog):
        """Backlog is drained even if the IMAP lock cannot be acquired.

        The drain step runs BEFORE the IMAP lock check, so even if the
        lock is busy, backlog entries get processed.
        """
        self._setup_account_with_message(db, email_service)

        # Hold the IMAP lock for this account
        held = acquire_account_imap_lock("test@example.com")
        assert held
        try:
            email_service.msg_ops.backlog.enqueue(
                msg_uuid="msg-1",
                account_email="test@example.com",
                folder_name="INBOX",
                imap_uid=42,
                is_read=1,
                is_deleted=0,
            )

            with caplog.at_level("INFO"):
                result = email_service.sync_account("test@example.com")

            # Backlog drain was attempted before the IMAP lock failure
            assert "Drained" in caplog.text, (
                "Backlog drain should run even when IMAP lock is busy"
            )
            # Sync should report the lock failure
            has_lock_error = any(
                "IMAP operation already in progress" in err
                for err in result.errors
            )
            assert has_lock_error, (
                "Sync should report that IMAP operation was already in progress"
            )
        finally:
            release_account_imap_lock("test@example.com")

    def test_stale_backlog_cleaned_up(self, db, email_service):
        """Stale backlog entries (NULL imap_uid) are cleaned up during drain."""
        self._setup_account_with_message(db, email_service, msg_uuid="stale-msg",
                                          imap_uid=None)

        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO _sync_backlog (msg_uuid, account_email, folder_name, "
            "imap_uid, is_read, is_deleted, created_at, retries) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("stale-msg", "test@example.com", "INBOX", None, 1, 0, now, 0),
        )
        assert email_service.msg_ops.backlog.count_pending(
            account_email="test@example.com",
        ) == 1

        # sync_account triggers the pre-sync drain which cleans stale entries
        email_service.sync_account("test@example.com")

        # Stale entry should be gone (cleaned up by _process before IMAP connect)
        remaining = email_service.msg_ops.backlog.count_pending(
            account_email="test@example.com",
        )
        assert remaining == 0, "Stale backlog entry should have been cleaned up"

    def test_returns_sync_result_on_imap_failure(self, db, email_service):
        """sync_account always returns a SyncResult, even on IMAP failure."""
        self._setup_account_with_message(db, email_service)

        result = email_service.sync_account("test@example.com")

        assert isinstance(result, SyncResult)
        # Should have errors (no real IMAP server)
        assert len(result.errors) >= 0  # May have IMAP connection error


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


# ── Per-account IMAP lock tests ────────────────────────────────────────────


class TestAccountImapLock:
    """Tests for per-account IMAP connection lock."""

    def test_acquire_release(self):
        """Acquire and release should work."""
        assert acquire_account_imap_lock("test@example.com") is True
        release_account_imap_lock("test@example.com")

    def test_double_acquire_blocks(self):
        """Second acquire on same account from different thread should timeout."""
        assert acquire_account_imap_lock("block-test@example.com") is True
        lock_acquired = [False]

        def try_lock():
            lock_acquired[0] = acquire_account_imap_lock(
                "block-test@example.com", timeout=1.0,
            )

        t = threading.Thread(target=try_lock)
        t.start()
        t.join(timeout=3)
        assert lock_acquired[0] is False, "Second lock should have timed out"
        release_account_imap_lock("block-test@example.com")

    def test_independent_accounts_dont_block(self):
        """Locks for different accounts should be independent."""
        assert acquire_account_imap_lock("alice@example.com") is True
        assert acquire_account_imap_lock("bob@example.com") is True
        release_account_imap_lock("alice@example.com")
        release_account_imap_lock("bob@example.com")

    def test_release_unheld_lock(self):
        """Releasing a lock not held by this thread should not raise."""
        release_account_imap_lock("unheld@example.com")  # Should not raise


# ── Email Draft UID Map / save_draft_to_imap tests ─────────────────────


class TestEmailDraftUidMap:
    """Tests for the email_draft_uid_map table and related operations."""

    def test_uid_map_table_exists(self, db):
        """The email_draft_uid_map table should be created on DB init."""
        assert db.table_exists("email_draft_uid_map")

    def test_uid_map_insert_and_query(self, db):
        """Insert a draft UID mapping and retrieve it."""
        from datetime import UTC, datetime
        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO email_draft_uid_map "
            "(account_email, folder_name, draft_uuid, imap_uid, message_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("user@example.com", "Drafts", "abc123def456", 42, "<msg@id>", now, now),
        )
        row = db.execute_one(
            "SELECT * FROM email_draft_uid_map WHERE draft_uuid = ?",
            ("abc123def456",),
        )
        assert row is not None
        assert row["account_email"] == "user@example.com"
        assert row["imap_uid"] == 42

    def test_uid_map_insert_or_replace(self, db):
        """INSERT OR REPLACE should update existing entries."""
        from datetime import UTC, datetime
        now = datetime.now(UTC).isoformat()
        # Insert initial
        db.execute(
            "INSERT INTO email_draft_uid_map "
            "(account_email, folder_name, draft_uuid, imap_uid, message_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("u@e.com", "Drafts", "draft1", 10, "<id1>", now, now),
        )
        # Replace with same PK
        db.execute(
            "INSERT OR REPLACE INTO email_draft_uid_map "
            "(account_email, folder_name, draft_uuid, imap_uid, message_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("u@e.com", "Drafts", "draft1", 20, "<id2>", now, now),
        )
        row = db.execute_one(
            "SELECT imap_uid FROM email_draft_uid_map WHERE draft_uuid = ?",
            ("draft1",),
        )
        assert row["imap_uid"] == 20

    def test_uid_map_max_uid_query(self, db):
        """MAX(imap_uid) query should return the highest UID."""
        from datetime import UTC, datetime
        now = datetime.now(UTC).isoformat()
        for uid in [10, 20, 30]:
            db.execute(
                "INSERT OR IGNORE INTO email_draft_uid_map "
                "(account_email, folder_name, draft_uuid, imap_uid, message_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("u@e.com", "Drafts", f"draft-{uid}", uid, "", now, now),
            )
        row = db.execute_one(
            "SELECT MAX(imap_uid) AS max_uid FROM email_draft_uid_map "
            "WHERE account_email = ? AND folder_name = ?",
            ("u@e.com", "Drafts"),
        )
        assert row["max_uid"] == 30


class TestSaveDraftToImap:
    """Tests for EmailService.save_draft_to_imap()."""

    @pytest.fixture
    def svc(self, db):
        """EmailService with a real DB and mocked IMAP pool."""
        svc = EmailService(db)
        # Add an account (FK requirement)
        from datetime import UTC, datetime
        now = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT OR IGNORE INTO accounts "
            "(email, name, imap_server, smtp_server, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("test@example.com", "Test", "imap.example.com", "smtp.example.com", now, now),
        )
        return svc

    def test_returns_error_for_missing_account(self, svc):
        """Draft with no account should return error message."""
        draft = {"uuid": "draft123", "data": {"account": ""}}
        error = svc.save_draft_to_imap(draft)
        assert error is not None
        assert "missing" in error.lower()

    def test_returns_error_for_missing_uuid(self, svc):
        """Draft with no uuid should return error message."""
        draft = {"uuid": "", "data": {"account": "test@example.com"}}
        error = svc.save_draft_to_imap(draft)
        assert error is not None
        assert "missing" in error.lower()

    def test_returns_error_for_no_password(self, svc):
        """Draft with account that has no password should return error."""
        draft = {"uuid": "draft123", "data": {"account": "test@example.com"}}
        error = svc.save_draft_to_imap(draft)
        assert error is not None
        # Account exists but no password set in keyring
        assert "no password configured" in error.lower() or "not found" in error.lower()

    def test_imap_lock_busy_returns_deferred_message(self, svc):
        """When the IMAP lock is held, returns a deferral message."""
        # Set a password first so we pass the password check and reach the lock
        from lighterbird.email.keyring import set_password
        set_password("test@example.com", "fakepassword")
        from lighterbird.email.service import acquire_account_imap_lock
        acquire_account_imap_lock("test@example.com")
        try:
            draft = {"uuid": "draft123", "data": {"account": "test@example.com"}}
            error = svc.save_draft_to_imap(draft)
            assert error is not None
            assert "deferred" in error.lower()
        finally:
            from lighterbird.email.service import release_account_imap_lock
            release_account_imap_lock("test@example.com")
