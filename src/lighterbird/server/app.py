"""FastAPI application factory for lighterbird."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

from lighterbird.server.middleware import add_middleware
from lighterbird.server.routes.admin import router as admin_router
from lighterbird.server.routes.calendar import router as calendar_router
from lighterbird.server.routes.chat import router as chat_router
from lighterbird.server.routes.command import router as command_router
from lighterbird.server.routes.contacts import router as contacts_router
from lighterbird.server.routes.cowrite import router as cowrite_router
from lighterbird.server.routes.drafts import router as drafts_router
from lighterbird.server.routes.embed import router as embed_router
from lighterbird.server.routes.email import router as email_router
from lighterbird.server.routes.email_actions import router as email_actions_router
from lighterbird.server.routes.email_blocks import router as email_blocks_router
from lighterbird.server.routes.email_spam import router as email_spam_router
from lighterbird.server.routes.email_sieve import router as email_sieve_router
from lighterbird.server.routes.email_sync import router as email_sync_router
from lighterbird.server.routes.email_undo import router as email_undo_router
from lighterbird.server.routes.journal import router as journal_router
from lighterbird.server.routes.letters import router as letters_router
from lighterbird.server.routes.llm import router as llm_router
from lighterbird.server.routes.profiles import router as profiles_router
from lighterbird.server.routes.prompt_commands import router as prompt_commands_router
from lighterbird.server.routes.render import router as render_router
from lighterbird.server.routes.tags import router as tags_router
from lighterbird.server.routes.todo import router as todo_router
from lighterbird.server.tasks import init_workers, shutdown_workers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler — seeds config defaults, starts/stops background workers."""
    # Seed default config files (system_prompt.md, cowrite_style.md, etc.) on startup
    try:
        from lighterbird.core.config_defaults import seed_config_defaults
        seed_config_defaults()
    except Exception:
        logger.warning("Config defaults seeding failed (non-fatal)")
    # Initialise the dedicated sync log file
    try:
        from lighterbird.core.sync_logger import init_sync_logger
        init_sync_logger()
    except Exception:
        logger.warning("Sync log initialisation failed (non-fatal)")
    workers = init_workers()
    app.state.worker_pool = workers

    # Initialise the sync state manager (tracks per-account sync status)
    try:
        from lighterbird.server.sync_state import init_sync_state_manager
        init_sync_state_manager()
        logger.info("[app] Sync state manager initialized")
    except Exception:
        logger.warning("[app] Sync state manager init failed (non-fatal)")

    yield
    shutdown_workers(timeout=5.0)
    # Clean up sync log handler
    try:
        from lighterbird.core.sync_logger import finalize as finalize_sync_logger
        finalize_sync_logger()
    except Exception:
        pass


def create_app(static_dir: str | Path | None = None) -> FastAPI:
    """Create and configure the lighterbird FastAPI application.

    Args:
        static_dir: Path to the built Svelte static files.
            If None, tries ``web/dist`` relative to the project root.

    Returns:
        Configured FastAPI instance.
    """
    app = FastAPI(
        title="lighterbird",
        version="0.2.0",
        description="Email, contacts, calendar, and todo — command-driven PIM",
        lifespan=lifespan,
    )

    # ── Middleware ───────────────────────────────────────────────────────
    add_middleware(app)

    # ── API routes ───────────────────────────────────────────────────────
    app.include_router(email_router)
    app.include_router(email_actions_router)
    app.include_router(email_blocks_router)
    app.include_router(email_spam_router)
    app.include_router(email_sieve_router)
    app.include_router(email_sync_router)
    app.include_router(email_undo_router)
    app.include_router(calendar_router)
    app.include_router(admin_router)
    app.include_router(command_router)
    app.include_router(contacts_router)
    app.include_router(todo_router)
    app.include_router(journal_router)
    app.include_router(chat_router)
    app.include_router(llm_router)
    app.include_router(drafts_router)
    app.include_router(letters_router)
    app.include_router(profiles_router)
    app.include_router(prompt_commands_router)
    app.include_router(cowrite_router)
    app.include_router(embed_router)
    app.include_router(render_router)
    app.include_router(tags_router)

    # ── Static files (Svelte SPA) ────────────────────────────────────────
    if static_dir is None:
        static_dir = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"

    static_path = Path(static_dir)
    if static_path.is_dir():
        app.mount("/", StaticFiles(directory=str(static_path), html=True), name="spa")
    else:
        logger.warning(
            "Static directory %s not found — frontend SPA unavailable. "
            "Build it with: cd web && npm run build",
            static_path,
        )

    return app


def main() -> None:
    """Run the development server."""
    import uvicorn

    port = int(os.environ.get("LIGHTERBIRD_PORT", 6006))
    debug = os.environ.get("LIGHTERBIRD_DEBUG", "").lower() in ("1", "true")
    uvicorn.run(
        "lighterbird.server.app:create_app",
        host="127.0.0.1",
        port=port,
        reload=debug,
        factory=True,
    )


if __name__ == "__main__":
    main()
