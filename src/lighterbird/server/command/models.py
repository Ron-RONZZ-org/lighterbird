"""Pydantic models for the command endpoint."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CommandRequest(BaseModel):
    """Request body for ``POST /api/v1/command``."""

    tokens: list[str]
    flags: dict[str, str] = {}
    raw_input: str = ""


class CommandResponse(BaseModel):
    """Standard response envelope for command execution."""

    type: str = "status"  # "status" | "email" | "events" | "contacts" | "help" | "error"
    title: str = ""
    data: Any = None
