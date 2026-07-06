"""Tests for calendar REST API routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from lighterbird.server.app import create_app


class TestCalendarEventsAPI:
    """Test /api/v1/calendar/events endpoints."""

    def _client(self):
        return TestClient(create_app())

    def test_list_events_empty(self):
        """GET /api/v1/calendar/events returns empty list."""
        resp = self._client().get("/api/v1/calendar/events")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert data["events"] == []

    def test_create_event(self):
        """Create a calendar, then create an event in it."""
        client = self._client()
        cal = client.post(
            "/api/v1/calendar/calendars",
            json={"url": "https://cal.example.com/cal", "username": "u", "password": "p", "remote": False},
        ).json()
        cal_uuid = cal["uuid"]

        resp = client.post(
            "/api/v1/calendar/events",
            json={
                "calendar_uuid": cal_uuid,
                "title": "Team Standup",
                "start": "2024-06-15T09:00:00+00:00",
                "end": "2024-06-15T09:30:00+00:00",
                "location": "Room 42",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Team Standup"
        assert data["location"] == "Room 42"
        assert "uuid" in data

    def test_create_and_get_event(self):
        """Create an event then retrieve it by UUID."""
        client = self._client()
        cal = client.post(
            "/api/v1/calendar/calendars",
            json={"url": "https://cal.example.com/cal", "username": "u", "password": "p", "remote": False},
        ).json()
        evt = client.post(
            "/api/v1/calendar/events",
            json={
                "calendar_uuid": cal["uuid"],
                "title": "Sync",
                "start": "2024-07-01T12:00:00+00:00",
                "end": "2024-07-01T13:00:00+00:00",
            },
        ).json()
        uuid = evt["uuid"]

        resp = client.get(f"/api/v1/calendar/events/{uuid}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "Sync"

    def test_get_nonexistent_event(self):
        """GET with unknown UUID returns 404."""
        resp = self._client().get("/api/v1/calendar/events/nonexistent")
        assert resp.status_code == 404

    def test_delete_event(self):
        """DELETE /api/v1/calendar/events/{uuid} returns 204."""
        client = self._client()
        cal = client.post(
            "/api/v1/calendar/calendars",
            json={"url": "https://cal.example.com/cal", "username": "u", "password": "p", "remote": False},
        ).json()
        evt = client.post(
            "/api/v1/calendar/events",
            json={
                "calendar_uuid": cal["uuid"],
                "title": "Delete Me",
                "start": "2024-08-01T12:00:00+00:00",
                "end": "2024-08-01T13:00:00+00:00",
            },
        ).json()

        resp = client.delete(f"/api/v1/calendar/events/{evt['uuid']}")
        assert resp.status_code == 204

    def test_update_event(self):
        """PATCH /api/v1/calendar/events/{uuid} updates fields."""
        client = self._client()
        cal = client.post(
            "/api/v1/calendar/calendars",
            json={"url": "https://cal.example.com/cal", "username": "u", "password": "p", "remote": False},
        ).json()
        evt = client.post(
            "/api/v1/calendar/events",
            json={
                "calendar_uuid": cal["uuid"],
                "title": "Original",
                "start": "2024-09-01T10:00:00+00:00",
                "end": "2024-09-01T11:00:00+00:00",
            },
        ).json()

        resp = client.patch(
            f"/api/v1/calendar/events/{evt['uuid']}",
            json={"title": "Updated Title", "location": "New Location"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"
        assert resp.json()["location"] == "New Location"
