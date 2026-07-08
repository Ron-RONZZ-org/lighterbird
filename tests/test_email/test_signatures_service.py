"""Tests for email/services/signatures.py — SignatureService with format support."""

from __future__ import annotations

from pathlib import Path

import pytest

from lighterbird.email.db import get_db
from lighterbird.email.services.signatures import SignatureService


@pytest.fixture
def db(tmp_path: Path):
    return get_db(tmp_path / "email.db")


@pytest.fixture
def svc(db):
    return SignatureService(db)


class TestSignatureServiceCreateWithFormat:
    def test_create_default_format(self, svc):
        """Creating a signature without format defaults to 'plain'."""
        sig = svc.create("work", "Best regards")
        assert sig["signature_format"] == "plain"
        assert sig["name"] == "work"

    def test_create_html_format(self, svc):
        sig = svc.create("html-sig", "<p>Best regards</p>", signature_format="html")
        assert sig["signature_format"] == "html"
        assert sig["signature_text"] == "<p>Best regards</p>"

    def test_create_markdown_format(self, svc):
        sig = svc.create("md-sig", "**Regards**", signature_format="markdown")
        assert sig["signature_format"] == "markdown"

    def test_create_invalid_format_raises(self, svc):
        with pytest.raises(ValueError, match="Invalid signature format"):
            svc.create("bad", "text", signature_format="xml")


class TestSignatureServiceUpdateFormat:
    def test_update_format(self, svc):
        sig = svc.create("test", "text", signature_format="plain")
        updated = svc.update(sig["uuid"], signature_format="html")
        assert updated["signature_format"] == "html"
        assert updated["signature_text"] == "text"  # unchanged

    def test_update_format_only(self, svc):
        sig = svc.create("test2", "text")
        updated = svc.update(sig["uuid"], signature_format="markdown")
        assert updated["signature_format"] == "markdown"
        assert updated["name"] == "test2"  # unchanged

    def test_update_invalid_format_raises(self, svc):
        sig = svc.create("test3", "text")
        with pytest.raises(ValueError, match="Invalid signature format"):
            svc.update(sig["uuid"], signature_format="pdf")


class TestSignatureServiceResolve:
    def test_resolve_returns_format(self, svc):
        sig = svc.create("default-sig", "Hello", signature_format="html")
        resolved = svc.resolve("test@example.com", name="default-sig")
        assert resolved is not None
        assert resolved["signature_format"] == "html"
        assert resolved["signature_text"] == "Hello"

    def test_resolve_missing_defaults_plain(self, svc, db):
        """If no format stored, defaults to 'plain'."""
        # Insert directly without format (simulating legacy data)
        import uuid
        from datetime import UTC, datetime

        db.execute(
            "INSERT INTO email_signatures (uuid, name, signature_text, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "legacy", "legacy text",
             datetime.now(UTC).isoformat(), datetime.now(UTC).isoformat()),
        )
        resolved = svc.resolve("x@y.com", name="legacy")
        assert resolved is not None
        assert resolved.get("signature_format", "plain") == "plain"

    def test_resolve_none_when_no_signatures(self, svc):
        resolved = svc.resolve("empty@example.com")
        assert resolved is None


class TestSignatureServiceListFormat:
    def test_list_includes_format(self, svc):
        svc.create("a", "text", signature_format="markdown")
        svc.create("b", "html", signature_format="html")
        sigs = svc.list_signatures()
        for s in sigs:
            assert "signature_format" in s
        html_sigs = [s for s in sigs if s["signature_format"] == "html"]
        assert len(html_sigs) >= 1
