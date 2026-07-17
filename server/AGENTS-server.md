# AGENTS-server.md — Server Module Agent Instructions

## Summary

Python web server for lighterbird. Serves the Svelte SPA, exposes a REST/WebSocket API for the frontend, and orchestrates background tasks (email sync, CalDAV sync).

## Purpose and Expected Behavior

`src/lighterbird/server/` provides:

- **`app.py`** — FastAPI application factory, startup/shutdown lifecycle.  On startup the ``lifespan`` handler calls :func:`~lighterbird.core.config_defaults.seed_config_defaults` to create any missing config files (``system_prompt.md``, ``cowrite_style.md``, ``cowrite_style_email.md``, ``cowrite_style_journal.md``, ``cowrite_style_todo.md``, ``cowrite_style_letter.md``) with their shipped defaults.
- **`routes/`** — API route handlers organized by domain (email, email_sync, email_actions, email_sieve, calendar, contacts, journal, todo, letter, profiles, chat, admin, cowrite)
- **`sync_progress.py`** — Thread-safe in-memory sync progress tracker used by the async sync endpoints. Provides ``SyncProgressTracker`` class and ``get_sync_progress_tracker()`` singleton.
- **`sync_state.py`** — Per-account sync state manager (thread-safe singleton) tracking startup sync completion and IDLE thread health. Provides ``SyncStateManager``, ``get_sync_state_manager()``, ``init_sync_state_manager()``.
- **`command/`** — `!` command system: tree definition, parser, registry, response models, per-domain handlers
- **`llm/`** — LLM integration: chat sessions, provider resolution, the shared **tool_loop** module (multi-round tool-calling loop with human-in-the-loop support), and the **`llm/tools/`** module (standalone LLM tool registry with 44 tools across 8 domains)
- **`cowrite/`** — AI-assisted writing integration for form editors
- **`middleware.py`** — CORS, error handling, request logging, static file serving
- **`deps.py`** — FastAPI dependency injection (get_db, get_email_service, get_db_for, etc.)
- **`schemas.py`** — Pydantic models for request/response validation
- **`tasks.py`** — Background task management (email polling, CalDAV sync, backup scheduler)

## Constraints and Invariants

- **The server is a single-user app** — no authentication middleware needed initially (future: optional auth)
- **Svelte SPA is served as static files** — the FastAPI app mounts `web/dist/` as static files
- **Multi-round tool-calling LLM chat** — `POST /api/v1/chat` uses a multi-round tool loop (`run_tool_loop` in `llm/tool_loop.py`) instead of one-shot command generation. The LLM receives all `!commands` as native tools and can iterate until it produces a final answer. WRITE-level tools gate behind user confirmation via `POST /api/v1/chat/resume`.
- **REST API for everything else** — messages, contacts, calendar, todo, journal, letters, profiles CRUD
- **Command system (`!` commands)** — the primary user interaction model. Defined in `command/tree.py`, dispatched by `command/registry.py`, handled by per-domain handlers in `command/handlers/`
- **Backup scheduler** — automatic timestamped backups of all domain databases on configurable schedule
- **Cowrite API** — AI-assisted writing via `POST /api/v1/cowrite`, used by form editors (ComposeEmail, TodoAddForm, JournalWrite, LetterForm).  Uses a **cascade style model**: a general ``cowrite_style.md`` file (cross-cutting rules) is loaded first, then a domain-specific file (``cowrite_style_email.md``, etc.) is appended based on the ``form_type`` parameter.
- **API version prefix**: `/api/v1/...`

## Input/Output Expectations

- `GET /api/v1/command/tree` — fetch command tree metadata (frontend bootstraps from this)
- `POST /api/v1/command/execute` — execute a `!` command, return structured response
- `GET /api/v1/email/messages` — list messages (filters: account, folder, read, starred)
- `GET /api/v1/email/messages/{uuid}` — get single message with body
- `POST /api/v1/email/sync` — trigger IMAP sync (synchronous, returns result directly — used by CLI command handler)
- `POST /api/v1/email/sync/start` — start async IMAP sync in background thread, returns `{ task_id }` immediately
- `GET /api/v1/email/sync/progress/{task_id}` — poll sync progress (`status`, `current_folder`, `total_folders`, `folder_name`, `total_messages`, `new_messages`, `errors`)
- `GET /api/v1/email/sync/status` — per-account sync state and whether startup sync is complete (polled by frontend every 10s to show ``SyncStatusBar``)
- `POST /api/v1/email/send` — send email (body: to, subject, body, cc, bcc, attachments, signature, signature_format, in_reply_to, save_as_sample)
- `GET /api/v1/email/signatures` — list all signatures with account-default enrichment (used by ComposeEmail and StatusPopup)
- `GET /api/v1/calendar/events` — list events (filter: date range, calendar)
- `POST /api/v1/calendar/events` — create event
- `GET /api/v1/contacts` — list/search contacts
- `GET /api/v1/journal/entries` — list journal entries
- `GET /api/v1/todo/tasks` — list/search tasks
- `GET /api/v1/letters/letters` — list letters
- `GET /api/v1/profiles` — list user profiles
- `POST /api/v1/cowrite` — AI-assisted writing
- `POST /api/v1/chat` — multi-round tool-calling chat (replaces old one-shot flow)
- `POST /api/v1/chat/resume` — resume paused HITL session after tool approval
- `GET /api/v1/chat/notice` — stale-commands notice
- `POST /api/v1/chat/stream` — (deprecated) SSE streaming without tool-calling
- `GET /api/v1/prompt-commands/list` — list prompt commands for autocomplete
- `POST /api/v1/prompt-commands/expand` — preview expanded prompt text
- `POST /api/v1/render-preview` — shared content-to-HTML conversion (markdown/html/plain) for preview rendering used by ComposeEmail, JournalWrite, LetterBodyEditor
- `POST /api/v1/email/preview` — compose full email preview HTML from subject, body, body_format, optional signature, and optional attachments (uses ``compose_email_html()`` internally). Returns ``{"html": "…"}``.
- `POST /api/v1/prompt-commands/execute` — expand + multi-round tool loop
- `POST /api/v1/prompt-commands/execute/resume` — resume paused HITL session
- `POST /api/v1/prompt-commands/execute/stream` — (deprecated) SSE without tool-calling
- `render_utils.py` — shared utilities: ``convert_to_html(content, fmt)`` for single-content conversion, ``compose_email_html(subject, body, body_format, signature_text, signature_format, attachments, attachment_base_url, full_document)`` for full email composition. ``compose_email_html()`` is used by both the preview endpoint and the SMTP send path for consistent rendering.

## Documentation Reference

- FastAPI docs: https://fastapi.tiangolo.com/
- Svelte SPA + FastAPI pattern: https://github.com/tecladocode/fastapi-svelte-spa

## LLM Tool Registry (`llm/tools/`)

The `llm/tools/` directory provides a **standalone LLM tool registry** with tools optimized for AI consumption:

- **`__init__.py`** — ``@llm_tool()`` decorator, ``get_llm_tools()`` (OpenAI format), ``dispatch_llm_tool()``, ``get_llm_tool_level()`` (permission callback for ``run_tool_loop``)
- **Domain modules** — each registers tools via ``@llm_tool()``: ``system.py`` (1 tool), ``email.py`` (13), ``calendar.py`` (10), ``contacts.py`` (5), ``todo.py`` (6), ``journal.py`` (4), ``letter.py`` (5) = **44 tools total**

Key design points:
1. **Direct domain service calls** — no CLI dispatch involvement, no flag parsing overhead
2. **Uniform return format** — ``{"success": True, "data": ...}`` or ``{"success": False, "error": "..."}``
3. **Dot-separated names** with underscore OpenAI format (``email.find`` ↔ ``email_find``) — compatible with ``tc_path()``
4. **Permission-gated** via ``get_llm_tool_level()`` callback passed as ``get_tool_level_fn`` to ``run_tool_loop()`` (from #247)
5. **UUID-based operations** (``email.read <uuid>``, ``todo.update``, etc.) — LLMs excel at UUID tracking
6. **Not yet wired into the chat endpoint** — that's Subissue 6 (#249)

## Domain-Specific Rules for Agents

1. **Thin route layer** — routes call into domain services and return JSON. No business logic in route handlers.
2. **Pydantic schemas for all I/O** — never return raw dicts from routes. Define request/response models in `schemas.py`.
3. **Multi-round tool loop for chat and prompt commands** — both `POST /api/v1/chat` and `POST /api/v1/prompt-commands/execute` use the shared `run_tool_loop()` from `lightercore.llm.tool_loop`. The LLM receives all `!commands` as native OpenAI-compatible tools and can iterate up to 20 rounds. READ-level tools execute silently; WRITE+ tools gate behind `confirm_tool` → `/chat/resume` (or `/execute/resume`).
4. **Error responses are structured JSON** — `{"error": "...", "code": "...", "suggestion": "..."}` (inspired by A-lien's actionable error messages).
5. **CORS is wide open in development** — restrictive in production (or behind a reverse proxy).
6. **Static file serving for production** — mount `web/dist/` at the root path. For development, use Svelte's Vite dev server with a proxy to FastAPI.
7. **Command system is the primary API.** All domain operations are accessible via `!commands`. REST routes exist for frontend convenience (list/search CRUD), but the command handler is the authoritative implementation.
8. **Register all interactive commands.** Any command that may be invoked with missing required args must be registered in `_INTERACTIVE_FORMS` (see root AGENTS.md) so the server can return a `form-required` response with pre-filled options.
9. **Backup covers all domain databases.** The backup scheduler auto-discovers `.db` files in the data directory — no need to register new databases manually.
10. **Unified email composition** — Use ``compose_email_html()`` from ``render_utils.py`` whenever an HTML email body needs to be produced from body + signature parts. This function is the single source of truth for email rendering, used by both ``POST /api/v1/email/preview`` and the SMTP send path (``msg_compose.py``). It delegates to ``convert_to_html()`` for per-part conversion, ensuring preview and send produce identical output.
11. **Form error handling** — ``FormTab.handleFormSubmit()`` in the frontend no longer opens an error tab on submission failure. Instead, it keeps the form open, preserves user input, and displays a red error banner above the form. Backend ``CommandValidationError`` messages (``error`` + ``suggestion``) are concatenated and shown in the banner. The ``submitting`` flag is cleared so the user can retry.
