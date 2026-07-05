"""Tests for calendar/caldav.py — CalDAV HTTP helpers, push, delete."""
from __future__ import annotations

import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from lighterbird.calendar.caldav import (
    _event_url,
    _parse_multistatus,
    delete_event,
    fetch_remote_calendar_payloads,
    http_fetch_text,
    probe_calendar_config,
    push_event,
    remote_http_url,
)


class TestRemoteHttpUrl:
    def test_http_unchanged(self):
        assert remote_http_url("http://example.com/cal") == "http://example.com/cal"

    def test_caldav_to_https(self):
        assert remote_http_url("caldav://example.com/cal") == "https://example.com/cal"

    def test_caldavs_to_https(self):
        assert remote_http_url("caldavs://example.com/cal") == "https://example.com/cal"

    def test_https_unchanged(self):
        assert remote_http_url("https://example.com/cal") == "https://example.com/cal"

    def test_strips_whitespace(self):
        assert remote_http_url("  caldav://example.com  ") == "https://example.com"


class TestHttpFetchText:
    @patch("urllib.request.urlopen")
    def test_successful_get(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"response body"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        status, body = http_fetch_text("https://example.com", "user", "pass")
        assert status == 200
        assert body == "response body"

    @patch("urllib.request.urlopen")
    def test_headers_passed(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"ok"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        status, body = http_fetch_text(
            "https://example.com", "u", "p",
            headers={"X-Custom": "val"},
        )
        assert status == 200

    @patch("urllib.request.urlopen", side_effect=urllib.error.URLError(TimeoutError("timeout")))
    def test_timeout_returns_0(self, mock_urlopen):
        status, body = http_fetch_text("https://example.com", "u", "p")
        assert status == 0

    def test_basic_auth_header(self):
        """Verify that the Authorization header is set correctly."""
        import base64
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.status = 200
            mock_resp.read.return_value = b"ok"
            mock_urlopen.return_value.__enter__.return_value = mock_resp

            http_fetch_text("https://example.com/cal", "alice", "secret")
            req = mock_urlopen.call_args[0][0]
            auth_header = req.get_header("Authorization")
            encoded = base64.b64encode(b"alice:secret").decode()
            assert auth_header == f"Basic {encoded}"

    @patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection failed"))
    def test_connection_error(self, mock_urlopen):
        status, body = http_fetch_text("https://example.com", "u", "p")
        assert status == 0


class TestParseMultistatus:
    MULTI_STATUS_XML = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:href>/cal/event1.ics</d:href>
    <c:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:event1
END:VEVENT
END:VCALENDAR</c:calendar-data>
  </d:response>
  <d:response>
    <d:href>/cal/event2.ics</d:href>
    <c:calendar-data>BEGIN:VCALENDAR
BEGIN:VEVENT
UID:event2
END:VEVENT
END:VCALENDAR</c:calendar-data>
  </d:response>
</d:multistatus>"""

    def test_parse_two_events(self):
        results = _parse_multistatus(self.MULTI_STATUS_XML)
        assert len(results) == 2
        assert results[0][0] == "/cal/event1.ics"
        assert "UID:event1" in results[0][1]
        assert results[1][0] == "/cal/event2.ics"
        assert "UID:event2" in results[1][1]

    def test_parse_empty_multistatus(self):
        xml = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
</d:multistatus>"""
        assert _parse_multistatus(xml) == []

    def test_parse_invalid_xml(self):
        assert _parse_multistatus("not xml") == []

    def test_parse_response_without_calendar_data(self):
        xml = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:href>/cal/event.ics</d:href>
  </d:response>
</d:multistatus>"""
        results = _parse_multistatus(xml)
        assert len(results) == 1
        assert results[0][0] == "/cal/event.ics"
        assert results[0][1] == ""


class TestFetchRemoteCalendarPayloads:
    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_successful_fetch(self, mock_http):
        multistatus = """<?xml version="1.0"?>
<d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
  <d:response>
    <d:href>/cal/event.ics</d:href>
    <c:calendar-data>BEGIN:VCALENDAR
UID:e1
END:VCALENDAR</c:calendar-data>
  </d:response>
</d:multistatus>"""
        mock_http.return_value = (207, multistatus)
        results = fetch_remote_calendar_payloads(
            "https://cal.example.com", "user", "pass",
        )
        assert len(results) == 1
        assert "UID:e1" in results[0][1]

    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_404_returns_empty(self, mock_http):
        mock_http.return_value = (404, "Not Found")
        results = fetch_remote_calendar_payloads(
            "https://cal.example.com", "user", "pass",
        )
        assert results == []

    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_non_207_raises(self, mock_http):
        mock_http.return_value = (500, "Server Error")
        with pytest.raises(RuntimeError, match="CalDAV fetch failed"):
            fetch_remote_calendar_payloads(
                "https://cal.example.com", "user", "pass",
            )


class TestEventUrl:
    def test_remote_href_absolute(self):
        url = _event_url("https://cal.example.com", "evt-uuid", "https://remote.example.com/evt.ics")
        assert url == "https://remote.example.com/evt.ics"

    def test_remote_href_relative(self):
        url = _event_url("https://cal.example.com/cal", "evt-uuid", "/cal/evt.ics")
        assert url == "https://cal.example.com/cal/evt.ics"

    def test_fallback_to_uuid(self):
        url = _event_url("https://cal.example.com/cal", "my-uuid")
        assert url == "https://cal.example.com/cal/my-uuid.ics"

    def test_no_remote_href_trailing_slash(self):
        url = _event_url("https://cal.example.com/cal/", "my-uuid")
        assert url == "https://cal.example.com/cal/my-uuid.ics"


class TestPushEvent:
    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_push_success_201(self, mock_http):
        mock_http.return_value = (201, "Created")
        status = push_event("https://cal.example.com", "u", "p", "ICS_DATA", "evt-uuid")
        assert status == 201

    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_push_success_204(self, mock_http):
        mock_http.return_value = (204, "")
        status = push_event("https://cal.example.com", "u", "p", "ICS_DATA", "evt-uuid")
        assert status == 204

    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_push_failure_raises(self, mock_http):
        mock_http.return_value = (403, "Forbidden")
        with pytest.raises(RuntimeError, match="CalDAV PUT failed"):
            push_event("https://cal.example.com", "u", "p", "ICS_DATA", "evt-uuid")

    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_push_with_remote_href(self, mock_http):
        mock_http.return_value = (200, "OK")
        push_event("https://cal.example.com", "u", "p", "ICS", "evt-uuid", remote_href="/cal/evt.ics")
        # Should use the remote_href URL
        call_kwargs = mock_http.call_args[0]
        assert "remote.example.com" not in str(call_kwargs[0])


class TestDeleteEvent:
    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_delete_success_200(self, mock_http):
        mock_http.return_value = (200, "OK")
        status = delete_event("https://cal.example.com", "u", "p", "evt-uuid")
        assert status == 200

    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_delete_404_accepted(self, mock_http):
        mock_http.return_value = (404, "Not Found")
        status = delete_event("https://cal.example.com", "u", "p", "evt-uuid")
        assert status == 404

    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_delete_failure_raises(self, mock_http):
        mock_http.return_value = (500, "Server Error")
        with pytest.raises(RuntimeError, match="CalDAV DELETE failed"):
            delete_event("https://cal.example.com", "u", "p", "evt-uuid")


class TestProbeCalendarConfig:
    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_probe_success(self, mock_http):
        mock_http.return_value = (200, "OK")
        with patch.object(
            __import__("lighterbird.calendar.caldav", fromlist=["fetch_remote_calendar_payloads"]),
            "fetch_remote_calendar_payloads",
            return_value=[("/e1.ics", "DATA")],
        ):
            result = probe_calendar_config("caldav://cal.example.com", "u", "p")
            assert result["count"] == "1"
            assert "1 event(s)" in result["description"]

    def test_probe_empty_username_raises(self):
        with pytest.raises(ValueError, match="Username is required"):
            probe_calendar_config("caldav://cal.example.com", "", "pass")

    def test_probe_empty_password_raises(self):
        with pytest.raises(ValueError, match="Password is required"):
            probe_calendar_config("caldav://cal.example.com", "user", "")

    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_probe_401_raises(self, mock_http):
        mock_http.return_value = (401, "Unauthorized")
        with pytest.raises(ValueError, match="Invalid username or password"):
            probe_calendar_config("caldav://cal.example.com", "u", "p")

    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_probe_403_raises(self, mock_http):
        mock_http.return_value = (403, "Forbidden")
        with pytest.raises(ValueError, match="Invalid username or password"):
            probe_calendar_config("caldav://cal.example.com", "u", "p")

    @patch("lighterbird.calendar.caldav.http_fetch_text")
    def test_probe_404_raises(self, mock_http):
        mock_http.return_value = (404, "Not Found")
        with pytest.raises(ValueError, match="Calendar not found at URL"):
            probe_calendar_config("caldav://cal.example.com", "u", "p")
