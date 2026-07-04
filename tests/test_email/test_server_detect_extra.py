"""Additional tests for email/server_detect.py — edge cases and coverage fill."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from lighterbird.email.server_detect import detect_servers, known_providers


class TestDetectServersAdditional:
    def test_yahoo_provider(self):
        result = detect_servers("user@yahoo.com")
        assert result["imap"] == "imap.mail.yahoo.com"

    def test_partial_explicit_smtp(self):
        result = detect_servers("user@outlook.com", smtp_server="custom.smtp.com")
        assert result["smtp"] == "custom.smtp.com"

    def test_protonmail_provider(self):
        result = detect_servers("user@protonmail.com")
        assert "imap" in result

    def test_gmx_provider(self):
        result = detect_servers("user@gmx.com")
        assert "imap" in result

    @patch("lighterbird.email.server_detect._lookup_mx")
    def test_mx_lookup_fallback_on_exception(self, mock_lookup_mx):
        """When _lookup_mx raises, the exception propagates."""
        mock_lookup_mx.side_effect = Exception("DNS failure")
        with pytest.raises(Exception, match="DNS failure"):
            detect_servers("user@customdomain.xyz")

    def test_known_providers_completeness(self):
        provs = known_providers()
        # Verify all entries have both imap and smtp
        for domain, svr in provs.items():
            assert "imap" in svr, f"Missing imap for {domain}"
            assert "smtp" in svr, f"Missing smtp for {domain}"
