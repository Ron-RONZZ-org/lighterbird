"""Pydantic schemas for all API request/response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

# ── Generic ──────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    code: str = ""
    suggestion: str = ""

    model_config = {"extra": "forbid"}


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.2.0"


# ── Email ────────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    email: str = Field(..., description="Email address")
    imap_server: str = Field(default="", description="IMAP server hostname")
    imap_port: int = Field(default=993, description="IMAP server port")
    imap_ssl: bool = Field(default=True, description="Use SSL for IMAP")
    smtp_server: str = Field(default="", description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_tls: bool = Field(default=True, description="Use STARTTLS for SMTP")
    password: str = Field(..., description="Account password")
    name: str = Field(default="", description="Display name for the account")

    model_config = {"extra": "forbid"}


class AccountResponse(BaseModel):
    email: str
    name: str
    imap_server: str
    imap_port: int
    smtp_server: str
    smtp_port: int
    created_at: str
    modified_at: str


class AccountListResponse(BaseModel):
    accounts: list[AccountResponse]


class SyncRequest(BaseModel):
    account_email: str | None = Field(default=None, description="Account email (or empty for all)")
    folder_name: str | None = Field(default=None, description="Only sync this folder (e.g. 'Trash'); requires account_email")
    folders_only: bool = Field(default=False, description="Only sync folder hierarchy, not message bodies")


class SyncResultResponse(BaseModel):
    total: int = 0
    new: int = 0
    errors: list[str] = []


class SyncAllResponse(BaseModel):
    results: dict[str, SyncResultResponse | dict]


class SyncStartResponse(BaseModel):
    """Response after starting an async sync task."""
    task_id: str
    account_email: str | None = None


class SyncProgressResponse(BaseModel):
    """Progress of a running/completed sync task."""
    task_id: str
    account_email: str
    status: str  # "running", "complete", "error"
    started_at: str
    completed_at: str | None = None
    total_folders: int = 0
    current_folder: int = 0
    folder_name: str = ""
    total_messages: int = 0
    new_messages: int = 0
    errors: list[str] = []


class MessageResponse(BaseModel):
    uuid: str
    account_email: str
    subject: str
    from_addr: str = Field(alias="from")
    to: list[str]
    body: str = ""
    html_body: str = ""
    is_read: bool
    received_at: str
    created_at: str

    model_config = {"populate_by_name": True, "extra": "ignore"}


class MessageListResponse(BaseModel):
    messages: list[dict[str, Any]]
    total: int


class SendRequest(BaseModel):
    account_email: str
    to: list[str]
    subject: str
    body: str = ""
    cc: list[str] = []
    bcc: list[str] = []
    priority: int = 3
    body_format: str = "markdown"  # "markdown" | "html" | "plain"
    attachments: list[dict] = []  # list of {"name": ..., "data": base64} dicts
    signature: str | None = None  # override signature; None = use account default
    signature_format: str = "plain"  # signature format: plain, html, or markdown
    in_reply_to: str | None = None  # Message-ID being replied to
    save_as_sample: bool = True  # save as writing sample for LLM style learning

    model_config = {"extra": "forbid"}


class MarkReadRequest(BaseModel):
    read: bool = True


class BatchDeleteRequest(BaseModel):
    uuids: list[str] = Field(..., min_length=1, max_length=200)

    model_config = {"extra": "forbid"}


class BatchMoveRequest(BaseModel):
    uuids: list[str] = Field(..., min_length=1, max_length=200)
    destination_folder: str = Field(..., min_length=1, description="Destination folder name")

    model_config = {"extra": "forbid"}


class BatchResultResponse(BaseModel):
    status: str = "ok"
    count: int
    errors: list[str] = Field(default_factory=list,
                              description="Per-UUID error messages for failed operations")


# ── Calendar ─────────────────────────────────────────────────────────────

class CalendarCreate(BaseModel):
    url: str = Field(..., description="CalDAV URL")
    username: str = Field(default="", description="Username")
    password: str = Field(default="", description="Password")
    remote: bool = Field(default=True, description="Whether this is a remote calendar")

    model_config = {"extra": "forbid"}


class CalendarResponse(BaseModel):
    uuid: str
    url: str
    username: str
    remote: bool


class CalendarListResponse(BaseModel):
    calendars: list[CalendarResponse]


class EventCreate(BaseModel):
    calendar_uuid: str
    title: str
    start: str = Field(..., description="ISO 8601 start datetime")
    end: str = Field(..., description="ISO 8601 end datetime")
    location: str = ""
    description: str = ""
    category: str = ""

    model_config = {"extra": "forbid"}


class EventResponse(BaseModel):
    uuid: str
    calendar_uuid: str
    title: str
    start: str
    end: str
    location: str
    description: str
    category: str


class EventListResponse(BaseModel):
    events: list[EventResponse]


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, description="Event title")
    start: str | None = Field(default=None, description="ISO 8601 start datetime")
    end: str | None = Field(default=None, description="ISO 8601 end datetime")
    location: str | None = Field(default=None, description="Location")
    description: str | None = Field(default=None, description="Description")
    category: str | None = Field(default=None, description="Category")

    model_config = {"extra": "forbid"}


class EventQueryParams(BaseModel):
    start: str = Field(default="2000-01-01", description="Start date (ISO)")
    end: str = Field(default="2099-12-31", description="End date (ISO)")
    calendar_uuid: str | None = Field(default=None, description="Calendar UUID filter")


# ── LLM ──────────────────────────────────────────────────────────────────

class LLMProfileCreate(BaseModel):
    name: str = Field(..., description="Profile name")
    provider_type: str = Field(..., description='Provider type: "openai", "deepseek", "ollama", or "custom"')
    api_key: str = Field(default="", description="API key")
    base_url: str = Field(default="", description="Base URL")
    model: str = Field(default="", description="Model name")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Temperature")
    max_tokens: int = Field(default=2048, ge=1, description="Max tokens")

    model_config = {"extra": "forbid"}


class LLMProfileResponse(BaseModel):
    name: str
    provider_type: str
    base_url: str
    model: str
    has_api_key: bool


class LLMProfileListResponse(BaseModel):
    profiles: list[LLMProfileResponse]


class LLMProfileUpdate(BaseModel):
    provider_type: str | None = Field(default=None, description='Provider type: "openai", "deepseek", "ollama", or "custom"')
    api_key: str | None = Field(default=None, description="API key (empty = keep current)")
    base_url: str | None = Field(default=None, description="Base URL")
    model: str | None = Field(default=None, description="Model name")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0, description="Temperature")
    max_tokens: int | None = Field(default=None, ge=1, description="Max tokens")

    model_config = {"extra": "forbid"}

    @field_validator("api_key")
    @classmethod
    def empty_api_key_is_none(cls, v: str | None) -> str | None:
        return v if v else None


# ── Account Updates ──────────────────────────────────────────────────────

class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, description="Display name")
    password: str | None = Field(default=None, description="Account password")
    imap_server: str | None = Field(default=None, description="IMAP server")
    smtp_server: str | None = Field(default=None, description="SMTP server")

    model_config = {"extra": "forbid"}


class CalendarUpdate(BaseModel):
    url: str | None = Field(default=None, description="CalDAV URL")
    username: str | None = Field(default=None, description="Username")
    password: str | None = Field(default=None, description="Password")

    model_config = {"extra": "forbid"}


# ── Sieve ─────────────────────────────────────────────────────────────────

class SieveScriptCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128, description="Script name (unique)")
    content: str = Field(default="", description="Sieve script source")

    model_config = {"extra": "forbid"}


class SieveScriptUpdate(BaseModel):
    name: str | None = Field(default=None, description="New script name (rename)")
    content: str | None = Field(default=None, description="New script content")

    model_config = {"extra": "forbid"}


class SieveActivateRequest(BaseModel):
    account_email: str = Field(..., description="Account email to activate/deactivate on")
    priority: int = Field(default=0, ge=0, le=999, description="Execution priority (0=lowest)")

    model_config = {"extra": "forbid"}


class SieveActivationInfo(BaseModel):
    active: bool
    priority: int = 0
    man_sync: bool
    created_at: str
    modified_at: str


class SievePriorityUpdate(BaseModel):
    account_email: str = Field(..., description="Account email")
    priority: int = Field(..., ge=0, le=999, description="New priority (0=lowest)")

    model_config = {"extra": "forbid"}


class SieveScriptEntry(BaseModel):
    name: str = Field(..., description="Script name")
    content: str = Field(default="", description="Script content")


class SieveCombineWarning(BaseModel):
    type: str
    message: str
    scripts: list[str] = []


class SieveAnalyzeRequest(BaseModel):
    account_email: str = Field(default="", description="Account email (for _spam_blocks injection)")
    scripts: list[SieveScriptEntry] = Field(..., description="Ordered list of scripts to combine")

    model_config = {"extra": "forbid"}


class SieveAnalyzeResponse(BaseModel):
    combined: str = ""
    warnings: list[SieveCombineWarning] = []
    is_valid: bool = True
    error: str = ""


class SieveScriptResponse(BaseModel):
    name: str
    content: str
    system: bool
    created_at: str
    modified_at: str
    aktivado: SieveActivationInfo | None = None


class SieveScriptListResponse(BaseModel):
    scripts: list[SieveScriptResponse]


class SieveValidateRequest(BaseModel):
    content: str = Field(..., description="Sieve script source to validate")

    model_config = {"extra": "forbid"}


class SieveValidateResponse(BaseModel):
    is_valid: bool
    error: str = ""


# ── Email Preview ──────────────────────────────────────────────────────

class EmailPreviewRequest(BaseModel):
    subject: str = ""
    body: str = ""
    body_format: str = "markdown"
    signature_text: str | None = None
    signature_format: str | None = None
    attachments: list[dict] = []

    model_config = {"extra": "forbid"}


class EmailPreviewResponse(BaseModel):
    html: str = ""
