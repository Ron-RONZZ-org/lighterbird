"""Tests for sync/flag_pull.py — FlagPuller, _flags_to_state, _merge, parsers."""

from __future__ import annotations

from pathlib import Path

import pytest

from lighterbird.email.sync.flag_pull import (
    _extract_flags,
    _extract_modseq,
    _extract_uid,
    _flags_to_state,
    _merge,
)


class TestFlagsToState:
    def test_empty_flags(self):
        assert _flags_to_state([]) == {"is_read": 0, "is_starred": 0}

    def test_seen_flag(self):
        assert _flags_to_state(["\\Seen"]) == {"is_read": 1, "is_starred": 0}

    def test_flagged(self):
        assert _flags_to_state(["\\Flagged"]) == {"is_read": 0, "is_starred": 1}

    def test_both(self):
        assert _flags_to_state(["\\Seen", "\\Flagged"]) == {"is_read": 1, "is_starred": 1}

    def test_other_flags_ignored(self):
        result = _flags_to_state(["\\Seen", "\\Answered", "$Forwarded"])
        assert result == {"is_read": 1, "is_starred": 0}


class TestMerge:
    def test_no_conflict(self):
        result = _merge(
            {"is_read": 1, "is_starred": 0},
            {"is_read": 0, "is_starred": 0},
            has_pending_backlog=False,
        )
        assert result == {"is_read": 1}

    def test_server_starred(self):
        result = _merge(
            {"is_read": 1, "is_starred": 1},
            {"is_read": 1, "is_starred": 0},
            has_pending_backlog=False,
        )
        assert result == {"is_starred": 1}

    def test_no_changes(self):
        result = _merge(
            {"is_read": 1, "is_starred": 0},
            {"is_read": 1, "is_starred": 0},
            has_pending_backlog=False,
        )
        assert result is None

    def test_pending_backlog_wins(self):
        """User intent wins over server state."""
        result = _merge(
            {"is_read": 1, "is_starred": 0},
            {"is_read": 0, "is_starred": 0},
            has_pending_backlog=True,
        )
        assert result is None

    def test_partial_merge(self):
        result = _merge(
            {"is_read": 1, "is_starred": 1},
            {"is_read": 1, "is_starred": 0},
            has_pending_backlog=False,
        )
        assert result == {"is_starred": 1}


class TestExtractUid:
    def test_basic(self):
        data = b"1 FETCH (UID 42 FLAGS (\\Seen))"
        assert _extract_uid(data) == 42

    def test_no_uid(self):
        data = b"1 FETCH (FLAGS (\\Seen))"
        assert _extract_uid(data) is None

    def test_empty(self):
        assert _extract_uid(b"") is None


class TestExtractFlags:
    def test_single_flag(self):
        data = b"1 FETCH (FLAGS (\\Seen) UID 1)"
        assert _extract_flags(data) == ["\\Seen"]

    def test_multiple_flags(self):
        data = b"1 FETCH (FLAGS (\\Seen \\Flagged) UID 1)"
        result = _extract_flags(data)
        assert "\\Seen" in result
        assert "\\Flagged" in result

    def test_no_flags(self):
        data = b"1 FETCH (UID 1)"
        assert _extract_flags(data) is None

    def test_empty_flags(self):
        data = b"1 FETCH (FLAGS () UID 1)"
        assert _extract_flags(data) == []

    def test_empty(self):
        assert _extract_flags(b"") is None


class TestExtractModseq:
    def test_rfc4551_format(self):
        """MODSEQ (N) format from RFC 4551."""
        data = b"1 FETCH (FLAGS (\\Seen) MODSEQ (12345) UID 42)"
        assert _extract_modseq(data) == 12345

    def test_alt_format(self):
        """MODSEQ N format (some servers)."""
        data = b"1 FETCH (FLAGS (\\Seen) MODSEQ 12345 UID 42)"
        assert _extract_modseq(data) == 12345

    def test_no_modseq(self):
        data = b"1 FETCH (FLAGS (\\Seen) UID 42)"
        assert _extract_modseq(data) is None

    def test_empty(self):
        assert _extract_modseq(b"") is None
