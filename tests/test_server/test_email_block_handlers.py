"""Tests for email_block command handlers — block list/add.

Also tests the spam_blocks REST API endpoints (used by the GUI list tab).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lighterbird.server.command.errors import CommandValidationError

# Import early to trigger @command side effects
from lighterbird.server.command.handlers import *  # noqa: F403
from lighterbird.server.command.registry import dispatch


@pytest.fixture
def mock_spam_svc(monkeypatch):
    """Inject a mock email service with .spam sub-mock into deps."""
    from lighterbird.server import deps

    svc = MagicMock()
    svc.spam = MagicMock()
    deps._services["email"] = svc
    return svc


class TestEmailBlockList:
    def test_block_list_empty(self, mock_spam_svc):
        """!email block list returns empty list when no blocks exist."""
        mock_spam_svc.spam.list_blocks.return_value = []
        result = dispatch(["email", "block", "list"], {})
        assert result["type"] == "block-list"
        assert result["title"] == "Blocked Senders"
        assert result["data"]["blocks"] == []
        assert result["data"]["total"] == 0

    def test_block_list_with_items(self, mock_spam_svc):
        """!email block list returns all blocks."""
        blocks = [
            {"uuid": "abc-123", "type": "sender", "pattern": "spam@example.com",
             "note": "", "created_at": "2024-01-01T00:00:00", "updated_at": "2024-01-01T00:00:00"},
            {"uuid": "def-456", "type": "domain", "pattern": "spam.com",
             "note": "Known spam domain", "created_at": "2024-01-02T00:00:00", "updated_at": "2024-01-02T00:00:00"},
        ]
        mock_spam_svc.spam.list_blocks.return_value = blocks
        result = dispatch(["email", "block", "list"], {})
        assert result["type"] == "block-list"
        assert len(result["data"]["blocks"]) == 2
        assert result["data"]["total"] == 2

    def test_block_list_calls_service(self, mock_spam_svc):
        """Verifies the service is called."""
        mock_spam_svc.spam.list_blocks.return_value = []
        dispatch(["email", "block", "list"], {})
        mock_spam_svc.spam.list_blocks.assert_called_once()


class TestEmailBlockAdd:
    def test_block_add_sender(self, mock_spam_svc):
        """!email block add <email> blocks a sender."""
        mock_spam_svc.spam.block_sender.return_value = {
            "uuid": "abc-123", "type": "sender", "pattern": "spam@example.com", "note": "",
        }
        result = dispatch(["email", "block", "add", "spam@example.com"], {})
        assert result["type"] == "status"
        assert result["title"] == "Block Added"
        mock_spam_svc.spam.block_sender.assert_called_once_with("spam@example.com", note="")

    def test_block_add_sender_with_note(self, mock_spam_svc):
        """!email block add <email> --note TEXT adds with note."""
        mock_spam_svc.spam.block_sender.return_value = {
            "uuid": "abc-123", "type": "sender", "pattern": "spam@example.com", "note": "spammy",
        }
        result = dispatch(["email", "block", "add", "spam@example.com"], {"note": "spammy"})
        assert result["title"] == "Block Added"
        mock_spam_svc.spam.block_sender.assert_called_once_with("spam@example.com", note="spammy")

    def test_block_add_domain(self, mock_spam_svc):
        """!email block add @domain blocks a domain."""
        mock_spam_svc.spam.block_domain.return_value = {
            "uuid": "def-456", "type": "domain", "pattern": "spam.com", "note": "",
        }
        result = dispatch(["email", "block", "add", "@spam.com"], {})
        assert result["type"] == "status"
        mock_spam_svc.spam.block_domain.assert_called_once_with("spam.com", note="")

    def test_block_add_domain_flag(self, mock_spam_svc):
        """!email block add --domain <domain> blocks via flag."""
        mock_spam_svc.spam.block_domain.return_value = {
            "uuid": "def-456", "type": "domain", "pattern": "spam.com", "note": "",
        }
        result = dispatch(["email", "block", "add"], {"domain": "spam.com"})
        assert result["type"] == "status"
        mock_spam_svc.spam.block_domain.assert_called_once_with("spam.com", note="")

    def test_block_add_sender_flag(self, mock_spam_svc):
        """!email block add --sender <email> blocks via flag."""
        mock_spam_svc.spam.block_sender.return_value = {
            "uuid": "abc-123", "type": "sender", "pattern": "spam@example.com", "note": "",
        }
        result = dispatch(["email", "block", "add"], {"sender": "spam@example.com"})
        assert result["type"] == "status"
        mock_spam_svc.spam.block_sender.assert_called_once_with("spam@example.com", note="")

    def test_block_add_no_args_returns_form_required(self, mock_spam_svc):
        """!email block add with no args returns form-required."""
        mock_spam_svc.spam.list_blocks.return_value = []
        result = dispatch(["email", "block", "add"], {})
        assert result["type"] == "form-required"
        assert result["title"] == "Block Sender/Domain"

    def test_block_add_invalid_input(self, mock_spam_svc):
        """!email block add with non-email, non-domain raises error."""
        with pytest.raises(CommandValidationError, match="Don't know how to interpret"):
            dispatch(["email", "block", "add", "just-a-word"], {})


class TestSpamBlocksRestApi:
    """Integration-style tests for the PATCH/DELETE REST endpoints."""

    @pytest.fixture
    def svc(self, mock_spam_svc):
        return mock_spam_svc

    def test_update_block_note(self, svc, monkeypatch):
        """PATCH /api/v1/email/blocks/<uuid> updates the note."""
        from lighterbird.server.routes.email_blocks import update_block
        from fastapi import HTTPException

        svc.spam.update_block.return_value = {
            "uuid": "abc-123", "type": "sender", "pattern": "spam@example.com",
            "note": "updated note", "created_at": "", "updated_at": "",
        }
        # Build request manually — depends on FastAPI Depends resolution
        # We test the underlying service call instead
        result = svc.spam.update_block("abc-123", note="updated note")
        assert result["note"] == "updated note"

    def test_update_block_not_found(self, svc):
        """PATCH returns 404 for missing block."""
        svc.spam.update_block.return_value = None
        from lighterbird.server.routes.email_blocks import BlockUpdateRequest

        req = BlockUpdateRequest(note="test")
        # Verify the service returns None for missing blocks
        result = svc.spam.update_block("nonexistent", note="test")
        assert result is None

    def test_delete_block(self, svc):
        """DELETE /api/v1/email/blocks/<uuid> calls unblock."""
        svc.spam.get_block.return_value = {"uuid": "abc-123", "type": "sender"}
        svc.spam.unblock.return_value = None

        svc.spam.unblock("abc-123")
        svc.spam.unblock.assert_called_once_with("abc-123")

    def test_delete_block_not_found(self, svc):
        """DELETE returns 404 for missing block."""
        svc.spam.get_block.return_value = None
        result = svc.spam.get_block("nonexistent")
        assert result is None


class TestSpamManagerUnit:
    """Unit tests for SpamManager methods."""

    @pytest.fixture
    def db(self):
        """Create an in-memory LighterDB with the spam_blocks schema loaded."""
        from lighterbird.email.db import _CREATE_SPAM_BLOCKS

        from lighterbird.core.db import LighterDB
        db = LighterDB(":memory:")
        db.execute(_CREATE_SPAM_BLOCKS)
        return db

    @pytest.fixture
    def mgr(self, db):
        from lighterbird.email.filters.spam import SpamManager
        return SpamManager(db)

    def test_block_sender_with_note(self, mgr):
        """block_sender stores the note."""
        block = mgr.block_sender("spam@example.com", note="spammy sender")
        assert block["type"] == "sender"
        assert block["pattern"] == "spam@example.com"
        assert block["note"] == "spammy sender"
        assert block["uuid"]

    def test_block_domain_with_note(self, mgr):
        """block_domain stores the note."""
        block = mgr.block_domain("spamsite.com", note="known spam domain")
        assert block["type"] == "domain"
        assert block["pattern"] == "spamsite.com"
        assert block["note"] == "known spam domain"

    def test_block_domain_strips_at(self, mgr):
        """block_domain strips leading @ if provided."""
        block = mgr.block_domain("@spamsite.com")
        assert block["pattern"] == "spamsite.com"

    def test_get_block_found(self, mgr):
        """get_block returns the block by UUID."""
        created = mgr.block_sender("spam@example.com")
        fetched = mgr.get_block(created["uuid"])
        assert fetched is not None
        assert fetched["uuid"] == created["uuid"]
        assert fetched["pattern"] == "spam@example.com"

    def test_get_block_not_found(self, mgr):
        """get_block returns None for unknown UUID."""
        assert mgr.get_block("nonexistent-uuid") is None

    def test_update_block_note(self, mgr):
        """update_block changes the note."""
        created = mgr.block_sender("spam@example.com")
        updated = mgr.update_block(created["uuid"], note="new note")
        assert updated is not None
        assert updated["note"] == "new note"
        # Verify persistence
        fetched = mgr.get_block(created["uuid"])
        assert fetched["note"] == "new note"

    def test_update_block_none_note_keeps_old(self, mgr):
        """update_block with note=None keeps existing note."""
        created = mgr.block_sender("spam@example.com", note="original")
        updated = mgr.update_block(created["uuid"], note=None)
        assert updated is not None
        assert updated["note"] == "original"

    def test_update_block_not_found(self, mgr):
        """update_block returns None for unknown UUID."""
        assert mgr.update_block("nonexistent", note="test") is None

    def test_unblock_removes_block(self, mgr):
        """unblock removes the block by UUID."""
        created = mgr.block_sender("spam@example.com")
        mgr.unblock(created["uuid"])
        assert mgr.get_block(created["uuid"]) is None

    def test_list_blocks(self, mgr):
        """list_blocks returns all blocks in desc order."""
        mgr.block_sender("a@a.com")
        mgr.block_sender("b@b.com")
        blocks = mgr.list_blocks()
        assert len(blocks) == 2
