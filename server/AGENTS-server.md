# AGENTS-server.md — Server Module Agent Instructions

## Summary

Python web server for lighterbird. Serves the Svelte SPA, exposes a REST/WebSocket API for the frontend, and orchestrates background tasks (email sync, CalDAV sync).

## Purpose and Expected Behavior

`src/lighterbird/server/` provides:

- **`app.py`** — FastAPI application factory, startup/shutdown lifecycle
- **`routes/`** — API route handlers organized by domain (email, calendar, admin)
- **`middleware/`** — CORS, error handling, request logging, static file serving
- **`deps.py`** — FastAPI dependency injection (get_db, get_email_service, etc.)
- **`schemas.py`** — Pydantic models for request/response validation
- **`tasks.py`** — Background task management (email polling, CalDAV sync)

## Constraints and Invariants

- **The server is a single-user app** — no authentication middleware needed initially (future: optional auth)
- **Svelte SPA is served as static files** — the FastAPI app mounts `web/dist/` as static files
- **WebSocket endpoint for streaming LLM responses** — the command bar needs real-time streaming
- **REST API for everything else** — messages, contacts, calendar, todo CRUD
- **One background thread for email sync** — polls IMAP accounts on configurable interval
- **One background thread for CalDAV sync** — processes the sync queue
- **API version prefix**: `/api/v1/...`

## Input/Output Expectations

- `GET /api/v1/email/messages` — list messages (filters: account, folder, read, starred)
- `GET /api/v1/email/messages/{uuid}` — get single message with body
- `POST /api/v1/email/sync` — trigger IMAP sync
- `POST /api/v1/email/send` — send email (body: to, subject, body, cc, bcc, attachments)
- `GET /api/v1/calendar/events` — list events (filter: date range, calendar)
- `POST /api/v1/calendar/events` — create event
- `GET /api/v1/ai/chat` — WebSocket for streaming LLM chat
- `POST /api/v1/ai/command` — execute a `!` command, return structured result

## Documentation Reference

- FastAPI docs: https://fastapi.tiangolo.com/
- Svelte SPA + FastAPI pattern: https://github.com/tecladocode/fastapi-svelte-spa

## Domain-Specific Rules for Agents

1. **Thin route layer** — routes call into email/calendar/core services and return JSON. No business logic in route handlers.
2. **Pydantic schemas for all I/O** — never return raw dicts from routes. Define request/response models in `schemas.py`.
3. **Streaming LLM responses** — use FastAPI's `StreamingResponse` or WebSocket for real-time LLM output. The command bar should show tokens as they arrive.
4. **Error responses are structured JSON** — `{"error": "...", "code": "...", "suggestion": "..."}` (inspired by A-lien's actionable error messages).
5. **CORS is wide open in development** — restrictive in production (or behind a reverse proxy).
6. **Static file serving for production** — mount `web/dist/` at the root path. For development, use Svelte's Vite dev server with a proxy to FastAPI.
