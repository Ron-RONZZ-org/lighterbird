"""FastAPI middleware — CORS, error handling."""

from __future__ import annotations

import os
import sqlite3

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from lighterbird.core.exceptions import LighterError

logger = logging.getLogger(__name__)


def _error_response(status: int, exc: Exception) -> JSONResponse:
    """Build a structured JSON error response."""
    suggestion = ""
    if hasattr(exc, "details"):
        suggestion = exc.details.get("suggestion", "")
    return JSONResponse(
        status_code=status,
        content={
            "error": str(exc),
            "code": type(exc).__name__,
            "suggestion": suggestion,
        },
    )


def add_middleware(app: FastAPI) -> None:
    """Register all middleware on the FastAPI application."""

    @app.exception_handler(LighterError)
    async def lighterbird_error_handler(request: Request, exc: LighterError):
        return _error_response(400, exc)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return _error_response(400, exc)

    @app.exception_handler(ConnectionError)
    async def connection_error_handler(request: Request, exc: ConnectionError):
        return _error_response(502, exc)

    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity_error_handler(request: Request, exc: sqlite3.IntegrityError):
        return _error_response(400, exc)

    @app.exception_handler(sqlite3.OperationalError)
    async def operational_error_handler(request: Request, exc: sqlite3.OperationalError):
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Database error: {exc}",
                "code": "DB_ERROR",
                "suggestion": (
                    "Try deleting the database file in ~/.local/share/lighterbird/ "
                    "or set LIGHTERBIRD_DIR to a fresh directory."
                ),
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception processing %s %s", request.method, request.url.path)
        if os.environ.get("LIGHTERBIRD_DEBUG"):
            raise  # Re-raise in dev so the traceback is visible
        # Return a generic message to avoid leaking internal details
        return JSONResponse(
            status_code=500,
            content={
                "error": "An internal error occurred.",
                "code": "INTERNAL_ERROR",
                "suggestion": (
                    "Enable LIGHTERBIRD_DEBUG=1 and check the server logs "
                    "for details."
                ),
            },
        )

    # CORS: allow all origins during development.
    # When deploying, set `LIGHTERBIRD_ORIGINS` env var to a comma-separated
    # list of allowed origins (e.g. "https://app.example.com").
    # Credentials + wildcard origin is invalid per CORS spec, so we only
    # allow credentials when explicit origins are configured.
    origins_str = os.environ.get("LIGHTERBIRD_ORIGINS", "*")
    origins = [o.strip() for o in origins_str.split(",") if o.strip()]
    has_credentials = origins != ["*"]

    # Warn loudly if wildcard CORS is used outside of debug mode — this is
    # a security risk if the server is exposed beyond localhost.
    if origins == ["*"] and not os.environ.get("LIGHTERBIRD_DEBUG"):
        logger.warning(
            "CORS is wide-open (allow_origins=*). "
            "Set LIGHTERBIRD_ORIGINS to a comma-separated list of allowed origins "
            "and LIGHTERBIRD_DEBUG=1 during development to suppress this warning."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=has_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
