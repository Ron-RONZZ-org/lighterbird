"""Tests for co-writing REST API route."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestCowriteAPI:
    """Test /api/v1/cowrite endpoint."""

    def _client(self):
        return TestClient(create_app())

    def test_missing_form_type(self):
        """POST /api/v1/cowrite without form_type returns 400."""
        resp = self._client().post(
            "/api/v1/cowrite",
            json={"fields": {"body": "Hello"}, "instruction": "Make it formal"},
        )
        assert resp.status_code == 400
        assert "form_type" in resp.text.lower()

    def test_missing_fields(self):
        """POST /api/v1/cowrite without fields returns 400."""
        resp = self._client().post(
            "/api/v1/cowrite",
            json={"form_type": "email-send", "instruction": "Make it formal"},
        )
        assert resp.status_code == 400
        assert "fields" in resp.text.lower()

    def test_missing_instruction(self):
        """POST /api/v1/cowrite without instruction returns 400."""
        resp = self._client().post(
            "/api/v1/cowrite",
            json={"form_type": "email-send", "fields": {"body": "Hello"}},
        )
        assert resp.status_code == 400
        assert "instruction" in resp.text.lower()

    def test_non_string_field_value(self):
        """POST /api/v1/cowrite with non-string field value returns 400."""
        resp = self._client().post(
            "/api/v1/cowrite",
            json={
                "form_type": "email-send",
                "fields": {"body": 123},
                "instruction": "Fix it",
            },
        )
        assert resp.status_code == 400

    def test_valid_request_no_llm(self):
        """POST /api/v1/cowrite with valid fields but no LLM returns 502."""
        resp = self._client().post(
            "/api/v1/cowrite",
            json={
                "form_type": "email-send",
                "fields": {"body": "Hello world", "subject": "Test"},
                "instruction": "Make it more professional",
            },
        )
        # Without LLM configured, the route returns a 502 or 422
        assert resp.status_code in (502, 422)
