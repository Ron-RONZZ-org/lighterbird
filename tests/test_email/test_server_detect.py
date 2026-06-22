"""Tests for server_detect — IMAP/SMTP auto-detection."""

from __future__ import annotations

from lighterbird.email.server_detect import detect_servers, known_providers, _lookup_mx


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

    def test_mx_lookup_ronzz_org(self):
        mx = _lookup_mx("ronzz.org")
        assert mx is not None
        assert "migadu.com" in mx.lower() or "aspmx" in mx.lower()

    def test_detect_via_mx_provider(self):
        """ronzz.org uses Migadu → should detect via MX + provider match."""
        result = detect_servers("user@ronzz.org")
        assert result["imap"] == "imap.migadu.com", (
            f"Expected Migadu IMAP, got {result['imap']}")
        assert result["smtp"] == "smtp.migadu.com", (
            f"Expected Migadu SMTP, got {result['smtp']}")
        assert result["method"] in ("known_provider", "mx_provider")

    def test_partial_explicit_imap(self):
        """Partial override: IMAP explicitly set, SMTP should auto-detect."""
        result = detect_servers("user@outlook.com", imap_server="custom.imap.com")
        assert result["imap"] == "custom.imap.com"
        assert result["smtp"] == "smtp.office365.com"  # from known provider
        assert result["method"] in ("explicit", "known_provider")
