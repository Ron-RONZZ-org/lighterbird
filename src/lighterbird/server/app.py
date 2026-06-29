"""FastAPI application factory for lighterbird."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from lighterbird.server.middleware import add_middleware
from lighterbird.server.routes.email import router as email_router
from lighterbird.server.routes.email_sieve import router as email_sieve_router
from lighterbird.server.routes.calendar import router as calendar_router
from lighterbird.server.routes.admin import router as admin_router
from lighterbird.server.routes.command import router as command_router
from lighterbird.server.routes.contacts import router as contacts_router
from lighterbird.server.routes.todo import router as todo_router
from lighterbird.server.routes.journal import router as journal_router
from lighterbird.server.routes.chat import router as chat_router
from lighterbird.server.routes.llm import router as llm_router
from lighterbird.server.routes.drafts import router as drafts_router
from lighterbird.server.tasks import init_workers, shutdown_workers


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler — starts/stops background workers."""
    workers = init_workers()
    app.state.worker_pool = workers
    yield
    shutdown_workers(timeout=5.0)


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
    app.include_router(email_sieve_router)
    app.include_router(calendar_router)
    app.include_router(admin_router)
    app.include_router(command_router)
    app.include_router(contacts_router)
    app.include_router(todo_router)
    app.include_router(journal_router)
    app.include_router(chat_router)
    app.include_router(llm_router)
    app.include_router(drafts_router)

    # ── Static files (Svelte SPA) ────────────────────────────────────────
    if static_dir is None:
        static_dir = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"

    static_path = Path(static_dir)
    if static_path.is_dir():
        app.mount("/", StaticFiles(directory=str(static_path), html=True), name="spa")

    return app


def main() -> None:
    """Run the development server."""
    import uvicorn

    uvicorn.run(
        "lighterbird.server.app:create_app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        factory=True,
    )


if __name__ == "__main__":
    main()
