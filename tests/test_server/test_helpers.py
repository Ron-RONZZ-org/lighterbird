"""Tests for server/command/helpers.py — UUID extraction, response builders, validation."""

from __future__ import annotations

import pytest

from lighterbird.server.command.errors import CommandValidationError
from lighterbird.server.command.helpers import (
    require_found,
    require_uuid,
    status_response,
)


class TestRequireUuid:
    def test_returns_first_token(self):
        assert require_uuid(["abc-123", "extra"]) == "abc-123"

    def test_empty_list_raises(self):
        with pytest.raises(CommandValidationError, match="Missing UUID"):
            require_uuid([])

    def test_custom_hint(self):
        with pytest.raises(CommandValidationError) as exc:
            require_uuid([], usage_hint="Usage: !letter view <uuid>")
        assert exc.value.suggestion == "Usage: !letter view <uuid>"


class TestRequireFound:
    def test_entity_found_no_raise(self):
        require_found({"uuid": "abc"}, "abc", "letter")  # should not raise

    def test_none_entity_raises(self):
        with pytest.raises(CommandValidationError, match="Letter not found"):
            require_found(None, "abc-1234", "letter")

    def test_default_entity_name(self):
        with pytest.raises(CommandValidationError, match="Entry not found"):
            require_found(None, "abc")

    def test_uuid_prefix_in_message(self):
        with pytest.raises(CommandValidationError) as exc:
            require_found(None, "abc-1234", "contact")
        assert "abc-1234" in str(exc.value)


class TestStatusResponse:
    def test_basic_response(self):
        resp = status_response("Done", "Task completed successfully")
        assert resp == {
            "type": "status",
            "title": "Done",
            "data": {"_summary": "Task completed successfully"},
        }

    def test_with_extra_data(self):
        resp = status_response("Sync", "Email sync done", extra={"count": 42})
        assert resp["type"] == "status"
        assert resp["title"] == "Sync"
        assert resp["data"]["_summary"] == "Email sync done"
        assert resp["data"]["count"] == 42

    def test_extra_none(self):
        resp = status_response("OK", "ok", extra=None)
        assert "_summary" in resp["data"]
        assert len(resp["data"]) == 1

    def test_empty_summary(self):
        resp = status_response("Empty", "")
        assert resp["data"]["_summary"] == ""
