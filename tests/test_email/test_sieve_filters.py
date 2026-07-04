"""Tests for email/filters — sieve validation, combiner, spam manager."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.email.filters.combiner import (
    combine_scripts,
    check_conflicts,
    _parse_require,
    _strip_require,
    _fileinto_targets,
)
from lighterbird.email.filters.sieve import validate_sieve
from lighterbird.email.filters.spam import SpamManager


# ── Sieve validation ─────────────────────────────────────────────────────────


class TestValidateSieve:
    def test_valid_sieve(self):
        valid = 'require ["fileinto"];\nif true { fileinto "INBOX"; }'
        is_valid, err = validate_sieve(valid)
        # Without sievelib installed, this returns (True, "")
        assert is_valid is True
        assert err == ""

    def test_empty_content(self):
        is_valid, err = validate_sieve("")
        assert is_valid is True


# ── Combiner ─────────────────────────────────────────────────────────────────


class TestCombineScripts:
    def test_combine_two_scripts(self):
        scripts = [
            {"name": "spam", "content": 'require ["fileinto"];\nif true { fileinto "Junk"; }'},
            {"name": "vacation", "content": 'require ["vacation"];\nvacation :days 3 "Away";'},
        ]
        combined, warnings = combine_scripts(scripts)
        assert 'require ["fileinto", "vacation"]' in combined
        assert "# === Script: spam ===" in combined
        assert "# === Script: vacation ===" in combined
        assert warnings == []

    def test_combine_deduplicates_require(self):
        scripts = [
            {"name": "a", "content": 'require ["fileinto"];\nfileinto "A";'},
            {"name": "b", "content": 'require ["fileinto"];\nfileinto "B";'},
        ]
        combined, _warnings = combine_scripts(scripts)
        # Should have only one require with fileinto
        assert combined.count("require [") == 1

    def test_empty_script_list(self):
        combined, warnings = combine_scripts([])
        # Still emits a header comment
        assert "Combined from 0 script(s)" in combined
        assert warnings == []

    def test_script_with_no_content(self):
        scripts = [{"name": "empty", "content": ""}]
        combined, warnings = combine_scripts(scripts)
        # Script with empty body is skipped, but header still shows count
        assert "Combined from 1 script(s)" in combined
        assert warnings == []

    def test_empty_name_script(self):
        scripts = [{"name": "", "content": "require [\"fileinto\"];\nfileinto \"X\";"}]
        combined, _warnings = combine_scripts(scripts)
        assert "# === Script:  ===" in combined

    def test_duplicate_fileinto_warning(self):
        scripts = [
            {"name": "a", "content": 'require ["fileinto"];\nfileinto "Target";'},
            {"name": "b", "content": 'require ["fileinto"];\nfileinto "Target";'},
        ]
        _combined, warnings = combine_scripts(scripts)
        dup_warnings = [w for w in warnings if w["type"] == "duplicate_fileinto"]
        assert len(dup_warnings) == 1
        assert "Target" in dup_warnings[0]["message"]

    def test_multiple_vacation_warning(self):
        scripts = [
            {"name": "a", "content": 'require ["vacation"];\nvacation :days 1 "A";'},
            {"name": "b", "content": 'require ["vacation"];\nvacation :days 1 "B";'},
        ]
        _combined, warnings = combine_scripts(scripts)
        vac_warnings = [w for w in warnings if w["type"] == "multiple_vacation"]
        assert len(vac_warnings) == 1

    def test_multiple_stop_warning(self):
        scripts = [
            {"name": "a", "content": "if true { stop; }"},
            {"name": "b", "content": "if false { stop; }"},
        ]
        _combined, warnings = combine_scripts(scripts)
        stop_warnings = [w for w in warnings if w["type"] == "multiple_stop"]
        assert len(stop_warnings) == 1


class TestCheckConflicts:
    def test_check_no_conflicts(self):
        scripts = [
            {"name": "a", "content": 'require ["fileinto"];\nfileinto "A";'},
        ]
        warnings = check_conflicts(scripts)
        assert warnings == []

    def test_check_duplicate_fileinto(self):
        scripts = [
            {"name": "a", "content": 'require ["fileinto"];\nfileinto "X";'},
            {"name": "b", "content": 'require ["fileinto"];\nfileinto "X";'},
        ]
        warnings = check_conflicts(scripts)
        assert any(w["type"] == "duplicate_fileinto" for w in warnings)


class TestCombinerHelpers:
    def test_parse_require(self):
        caps = _parse_require('require ["fileinto", "vacation"];')
        assert caps == {"fileinto", "vacation"}

    def test_parse_require_none(self):
        assert _parse_require("if true {}") == set()

    def test_parse_require_empty_brackets(self):
        assert _parse_require("require [];") == set()

    def test_strip_require(self):
        rest = _strip_require('require ["fileinto"];\nfileinto "Junk";')
        assert "require" not in rest
        assert 'fileinto "Junk"' in rest

    def test_strip_require_no_require(self):
        text = "if true {}"
        assert _strip_require(text) == text

    def test_fileinto_targets(self):
        targets = _fileinto_targets('fileinto "INBOX";\nfileinto "Junk";')
        assert targets == {"INBOX", "Junk"}

    def test_fileinto_targets_none(self):
        assert _fileinto_targets("if true {}") == set()


# ── SpamManager ──────────────────────────────────────────────────────────────


class TestSpamManager:
    @pytest.fixture
    def db(self, tmp_path: Path):
        """Create a LighterbirdDB with spam_blocks table."""
        from lighterbird.core.db import LighterbirdDB

        db_path = tmp_path / "spam_test.db"
        db = LighterbirdDB(db_path)
        db.execute(
            "CREATE TABLE IF NOT EXISTS spam_blocks ("
            "  uuid TEXT PRIMARY KEY,"
            "  type TEXT NOT NULL,"
            "  pattern TEXT NOT NULL,"
            "  created_at TEXT,"
            "  updated_at TEXT"
            ")"
        )
        return db

    @pytest.fixture
    def manager(self, db):
        return SpamManager(db)

    def test_block_sender(self, manager, db):
        block = manager.block_sender("spammer@example.com")
        assert block["type"] == "sender"
        assert block["pattern"] == "spammer@example.com"

        blocks = manager.list_blocks()
        assert len(blocks) == 1

    def test_block_domain(self, manager):
        block = manager.block_domain("spam.example.com")
        assert block["type"] == "domain"
        assert block["pattern"] == "spam.example.com"

    def test_block_domain_strips_at(self, manager):
        block = manager.block_domain("@spam.example.com")
        assert block["pattern"] == "spam.example.com"

    def test_unblock(self, manager):
        block = manager.block_sender("test@example.com")
        manager.unblock(block["uuid"])
        assert manager.list_blocks() == []

    def test_list_blocks_empty(self, manager):
        assert manager.list_blocks() == []

    def test_to_sieve_empty(self, manager):
        assert manager.to_sieve() == ""

    def test_to_sieve_with_blocks(self, manager):
        manager.block_sender("spammer@example.com")
        manager.block_domain("spamsite.com")
        sieve = manager.to_sieve()
        assert 'require ["reject", "envelope"]' in sieve
        assert "spammer@example.com" in sieve
        assert "spamsite.com" in sieve
        assert 'reject "Blocked sender:' in sieve
        assert 'reject "Blocked domain:' in sieve

    def test_to_sieve_sender_format(self, manager):
        manager.block_sender("bad@example.com")
        sieve = manager.to_sieve()
        assert 'envelope :contains "from" "bad@example.com"' in sieve
        assert 'reject "Blocked sender: bad@example.com"' in sieve

    def test_to_sieve_domain_format(self, manager):
        manager.block_domain("spam.com")
        sieve = manager.to_sieve()
        assert 'envelope :matches "from" "*@spam.com"' in sieve
        assert 'reject "Blocked domain: spam.com"' in sieve
