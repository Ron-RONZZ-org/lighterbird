"""Tests for server_detect — IMAP/SMTP auto-detection."""

from __future__ import annotations

from unittest.mock import patch

from lighterbird.email.server_detect import detect_servers, known_providers, _lookup_mx


def _fake_mx_answer(hostname: str, preference: int = 10):
    """Create a mock DNS MX answer object with the given hostname."""
    import dns.name

    class FakeAnswer:
        def __init__(self):
            self.exchange = dns.name.from_text(hostname)
            self.preference = preference

    return FakeAnswer()


class TestDetectServers:
    def test_known_provider_gmail(self):
        result = detect_servers("user@gmail.com")
        assert result["imap"] == "imap.gmail.com"
        assert result["smtp"] == "smtp.gmail.com"
        assert result["method"] == "known_provider"

    def test_known_provider_outlook(self):
        result = detect_servers("user@outlook.com")
        assert result["imap"] == "outlook.office365.com"
        assert result["smtp"] == "smtp.office365.com"

    def test_known_provider_migadu(self):
        result = detect_servers("user@migadu.com")
        assert result["imap"] == "imap.migadu.com"
        assert result["smtp"] == "smtp.migadu.com"

    def test_explicit_servers_override(self):
        result = detect_servers(
            "user@example.com",
            imap_server="custom.imap.com",
            smtp_server="custom.smtp.com",
        )
        assert result["imap"] == "custom.imap.com"
        assert result["smtp"] == "custom.smtp.com"
        assert result["method"] == "explicit"

    def test_explicit_imap_only(self):
        result = detect_servers("user@example.com", imap_server="my.imap.com")
        assert result["imap"] == "my.imap.com"
        assert "smtp" in result

    def test_fallback_domain_pattern(self):
        result = detect_servers("user@someobscuredomain.xyz")
        assert result["imap"] == "imap.someobscuredomain.xyz"
        assert isinstance(result["smtp"], str)
        assert len(result["smtp"]) > 0

    def test_invalid_email(self):
        import pytest
        with pytest.raises(ValueError, match="Invalid email"):
            detect_servers("not-an-email")
        with pytest.raises(ValueError, match="Invalid email"):
            detect_servers("")

    def test_known_providers_list(self):
        prov = known_providers()
        assert "gmail.com" in prov
        assert "outlook.com" in prov
        assert "yahoo.com" in prov
        assert "migadu.com" in prov
        for _domain, servers in prov.items():
            assert "imap" in servers
            assert "smtp" in servers

    @patch("dns.resolver.resolve")
    def test_mx_lookup(self, mock_resolve):
        """_lookup_mx returns the highest-priority MX hostname."""
        mock_resolve.return_value = [
            _fake_mx_answer("alt1.aspmx.migadu.com", preference=20),
            _fake_mx_answer("aspmx1.migadu.com", preference=10),
        ]
        mx = _lookup_mx("example.org")
        assert mx == "aspmx1.migadu.com"

    @patch("dns.resolver.resolve")
    def test_mx_lookup_no_records(self, mock_resolve):
        """_lookup_mx returns None when no MX records exist."""
        mock_resolve.side_effect = Exception("No MX record")
        mx = _lookup_mx("nonexistent.example")
        assert mx is None

    @patch("lighterbird.email.server_detect._lookup_mx")
    def test_detect_via_mx_provider(self, mock_lookup_mx):
        """When MX matches a known provider, detect via MX + provider match."""
        mock_lookup_mx.return_value = "aspmx1.migadu.com"
        result = detect_servers("user@ronzz.org")
        assert result["imap"] == "imap.migadu.com", (
            f"Expected Migadu IMAP, got {result['imap']}")
        assert result["smtp"] == "smtp.migadu.com", (
            f"Expected Migadu SMTP, got {result['smtp']}")
        assert result["method"] == "mx_provider"

    @patch("lighterbird.email.server_detect._lookup_mx")
    def test_detect_via_mx_provider_no_mx(self, mock_lookup_mx):
        """When MX lookup fails, falls back to domain pattern."""
        mock_lookup_mx.return_value = None
        # ronzz.org is not a known_provider by exact domain, so without MX
        # it should fall back to imap.ronzz.org / smtp.ronzz.org
        result = detect_servers("user@ronzz.org")
        assert result["method"] == "fallback"
        assert result["imap"] == "imap.ronzz.org"

    def test_partial_explicit_imap(self):
        """Partial override: IMAP explicitly set, SMTP should auto-detect."""
        result = detect_servers("user@outlook.com", imap_server="custom.imap.com")
        assert result["imap"] == "custom.imap.com"
        assert result["smtp"] == "smtp.office365.com"  # from known provider
        assert result["method"] in ("explicit", "known_provider")
