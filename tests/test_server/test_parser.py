"""Tests for server-side command parser."""
from __future__ import annotations

import pytest

from lighterbird.server.command.parser import parse_expanded


class TestParseExpanded:
    def test_basic_tokens(self):
        tokens, flags = parse_expanded("email list")
        assert tokens == ["email", "list"]
        assert flags == {}

    def test_leading_bang_stripped(self):
        tokens, flags = parse_expanded("!todo add buy milk")
        assert tokens == ["todo", "add", "buy", "milk"]
        assert flags == {}

    def test_double_quoted_token(self):
        tokens, flags = parse_expanded('email send "John Doe" hello')
        assert tokens == ["email", "send", "John Doe", "hello"]
        assert flags == {}

    def test_flag_long(self):
        tokens, flags = parse_expanded("email list --folder INBOX")
        assert tokens == ["email", "list"]
        assert flags == {"folder": "INBOX"}

    def test_flag_inline_value(self):
        tokens, flags = parse_expanded("email list --folder=INBOX")
        assert tokens == ["email", "list"]
        assert flags == {"folder": "INBOX"}

    def test_multiple_flags(self):
        tokens, flags = parse_expanded(
            "todo add --priority 3 --due 2024-12-31"
        )
        assert tokens == ["todo", "add"]
        assert flags == {"priority": "3", "due": "2024-12-31"}

    def test_boolean_flag(self):
        tokens, flags = parse_expanded("email sync --force")
        assert tokens == ["email", "sync"]
        assert flags == {"force": "true"}

    def test_boolean_flag_in_middle(self):
        tokens, flags = parse_expanded("email sync --force --folder INBOX")
        assert tokens == ["email", "sync"]
        assert flags == {"force": "true", "folder": "INBOX"}

    def test_short_flag(self):
        tokens, flags = parse_expanded("email list -f INBOX")
        assert tokens == ["email", "list"]
        assert flags == {"f": "INBOX"}

    def test_empty_input(self):
        tokens, flags = parse_expanded("")
        assert tokens == []
        assert flags == {}

    def test_only_whitespace(self):
        tokens, flags = parse_expanded("   ")
        assert tokens == []
        assert flags == {}

    def test_flag_with_no_value_treated_as_boolean(self):
        tokens, flags = parse_expanded("cmd --verbose")
        assert tokens == ["cmd"]
        assert flags == {"verbose": "true"}

    def test_mixed_quoted_and_flags(self):
        tokens, flags = parse_expanded(
            'contacts add "John Smith" john@example.com --phone +123'
        )
        assert tokens == ["contacts", "add", "John Smith", "john@example.com"]
        assert flags == {"phone": "+123"}

    def test_flag_after_trailing_boolean(self):
        """A flag at the end without a value should be boolean."""
        tokens, flags = parse_expanded("cmd sub --flag1 val1 --flag2")
        assert tokens == ["cmd", "sub"]
        assert flags == {"flag1": "val1", "flag2": "true"}

    def test_inline_flag_in_middle(self):
        tokens, flags = parse_expanded("cmd --debug=1 sub")
        assert tokens == ["cmd", "sub"]
        assert flags == {"debug": "1"}
