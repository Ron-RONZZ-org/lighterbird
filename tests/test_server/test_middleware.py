"""Tests for server/middleware.py — error handlers via TestClient."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from lighterbird.core.exceptions import LighterbirdError
from lighterbird.server.middleware import _error_response, add_middleware


class TestErrorResponse:
    def test_basic_error(self):
        resp = _error_response(400, ValueError("Bad input"))
        assert resp.status_code == 400
        data = resp.body.decode()
        assert "Bad input" in data
        assert "ValueError" in data

    def test_with_suggestion(self):
        class ExWithDetails(LighterbirdError):
            def __init__(self):
                super().__init__("Custom error")
                self.details = {"suggestion": "Try something else"}

        resp = _error_response(400, ExWithDetails())
        data = resp.body.decode()
        assert "Try something else" in data


class TestMiddlewareErrorHandlers:
    """Test error handlers via their actual FastAPI exception handling."""

    @pytest.fixture
    def app(self):
        app = FastAPI()
        add_middleware(app)

        @app.get("/raise-lighterbird")
        async def _raise_lighterbird():
            raise LighterbirdError("App error")

        @app.get("/raise-value")
        async def _raise_value():
            raise ValueError("Bad value")

        @app.get("/raise-connection")
        async def _raise_connection():
            raise ConnectionError("Connection lost")

        @app.get("/raise-integrity")
        async def _raise_integrity():
            import sqlite3
            raise sqlite3.IntegrityError("UNIQUE constraint")

        @app.get("/raise-operational")
        async def _raise_operational():
            import sqlite3
            raise sqlite3.OperationalError("database is locked")

        @app.get("/raise-generic")
        async def _raise_generic():
            raise RuntimeError("Unexpected")

        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_lighterbird_error(self, client):
        resp = client.get("/raise-lighterbird")
        assert resp.status_code == 400
        assert "App error" in resp.text

    def test_value_error(self, client):
        resp = client.get("/raise-value")
        assert resp.status_code == 400
        assert "Bad value" in resp.text

    def test_connection_error(self, client):
        resp = client.get("/raise-connection")
        assert resp.status_code == 502
        assert "Connection lost" in resp.text

    def test_integrity_error(self, client):
        resp = client.get("/raise-integrity")
        assert resp.status_code == 400
        assert "UNIQUE constraint" in resp.text

    def test_operational_error(self, client):
        resp = client.get("/raise-operational")
        assert resp.status_code == 500
        assert "database is locked" in resp.text
        assert "DB_ERROR" in resp.text

    def test_global_handler_structure(self):
        """Verify the global handler returns the right structure (_error_response)."""
        resp = _error_response(500, RuntimeError("Unexpected"))
        assert resp.status_code == 500
        data = resp.body.decode()
        assert "RuntimeError" in data
        assert "Unexpected" in data
