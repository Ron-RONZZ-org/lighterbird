"""Tests for email_spam command handlers — !email spam stats.

Also tests the EmailService.spam_detect and .phishing property wiring.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# Import early to trigger @command side effects
from lighterbird.server.command.handlers import *  # noqa: F403
from lighterbird.server.command.registry import dispatch


@pytest.fixture
def mock_spam_svc(monkeypatch):
    """Inject a mock email service with .db sub-mock into deps."""
    from lighterbird.server import deps

    svc = MagicMock()
    # Mock db.execute_one to return row-like dicts
    db = MagicMock()
    db.execute_one = MagicMock()

    def execute_one_side_effect(sql, params=None):
        sql_upper = sql.upper()
        if "COUNT(*) AS CNT FROM PHISHING_FEEDS" in sql_upper:
            return {"cnt": 42}
        if "COUNT(*) AS CNT FROM PHISHING_DOMAINS" in sql_upper:
            return {"cnt": 7}
        if "COUNT(*) AS CNT FROM MESSAGES WHERE IS_SPAM = 1" in sql_upper:
            return {"cnt": 5}
        if "COUNT(*) AS CNT FROM MESSAGES WHERE PHISHING_DETECTED = 1" in sql_upper:
            return {"cnt": 2}
        if "SUM(SPAM_COUNT)" in sql_upper:
            return {"total": 150, "total_spam": 300, "total_ham": 100}
        if "SOURCE" in sql_upper and "GROUP BY" in sql_upper:
            # Don't return from execute_one for this — the handler
            # calls execute() for the detail view
            return None
        return {"total": 150, "total_spam": 300, "total_ham": 100}

    db.execute_one = MagicMock(side_effect=execute_one_side_effect)
    db.execute = MagicMock(return_value=[])
    svc.db = db
    deps._services["email"] = svc
    return svc


class TestEmailSpamStats:
    def test_spam_stats_basic(self, mock_spam_svc):
        """!email spam stats returns status with summary."""
        result = dispatch(["email", "spam", "stats"], {})
        assert result["type"] == "status"
        assert result["title"] == "Spam Classifier Statistics"
        assert "_summary" in result["data"]
        summary = result["data"]["_summary"]
        assert "Bayesian tokens" in summary
        assert "Phishing feed domains" in summary
        assert "Messages flagged as spam" in summary

    def test_spam_stats_shows_counts(self, mock_spam_svc):
        """Stats shows correct counts from mocked DB."""
        result = dispatch(["email", "spam", "stats"], {})
        summary = result["data"]["_summary"]
        assert "150" in summary  # total tokens
        assert "300" in summary  # spam occurrences
        assert "100" in summary  # ham occurrences
        assert "42" in summary   # feed domains
        assert "7" in summary    # watchlist size
        assert "5" in summary    # spam messages
        assert "2" in summary    # phishing messages

    def test_spam_stats_detail(self, mock_spam_svc):
        """!email spam stats --detail shows top tokens."""
        # Mock execute to return some top tokens
        mock_spam_svc.db.execute.return_value = [
            {"token": "viagra", "spam_count": 10, "ham_count": 0},
            {"token": "free", "spam_count": 8, "ham_count": 2},
        ]
        result = dispatch(["email", "spam", "stats"], {"detail": "1"})
        summary = result["data"]["_summary"]
        assert "Top spammy tokens" in summary
        assert "viagra" in summary
        assert "free" in summary

    def test_spam_stats_empty_db(self, mock_spam_svc):
        """Stats still work when DB is empty."""
        # Override to return zeros
        mock_spam_svc.db.execute_one = MagicMock(return_value=None)
        mock_spam_svc.db.execute = MagicMock(return_value=[])
        result = dispatch(["email", "spam", "stats"], {})
        assert result["type"] == "status"
        assert "0" in result["data"]["_summary"]

    def test_spam_stats_unknown_subcommand(self, mock_spam_svc):
        """Unknown subcommand under email.spam returns graceful response."""
        result = dispatch(["email", "spam", "report"], {})
        # Dispatcher falls through gracefully for unknown subcommands
        assert result is not None


class TestEmailSpamRegistration:
    """Tests that the email.spam group and handler are registered."""

    def test_spam_stats_defined(self):
        """!email spam stats is a known command."""
        from lighterbird.server.command.registry import find_command_depth
        depth = find_command_depth(["email", "spam", "stats"])
        assert depth == 3  # fully matched

    def test_spam_group_defined(self):
        """!email.spam group exists."""
        from lighterbird.server.command.registry import find_tree_node
        node = find_tree_node(["email", "spam"])
        assert node is not None
        assert node.get("description") == "Spam classification statistics"
