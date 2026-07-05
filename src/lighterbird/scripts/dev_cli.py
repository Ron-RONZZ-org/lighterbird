"""CLI entry point for ``lighterbird-dev`` — isolated dev server with seed data.

Usage::

    # Start isolated server with seed data from .dev
    uv run lighterbird-dev --seed

    # Start isolated server without seed data
    uv run lighterbird-dev

    # Start isolated server, restore seed from a backup archive
    uv run lighterbird-dev --seed-from path/to/backup.7z
"""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path


def _find_dot_dev() -> Path | None:
    """Find the ``.dev`` file by walking up from the project root."""
    # The dev CLI script lives at src/lighterbird/scripts/dev_cli.py
    # Project root is ../../../../
    candidate = Path(__file__).resolve().parent.parent.parent.parent / ".dev"
    return candidate if candidate.exists() else None


def dev_main() -> None:
    """Run an isolated lighterbird development server.

    Creates a temporary data directory (``/tmp/lighterbird-dev-*``) and
    optionally seeds it with test data before starting the server.
    """
    parser = argparse.ArgumentParser(
        description="Run an isolated lighterbird development server.",
    )
    parser.add_argument(
        "--seed",
        nargs="?",
        const="auto",
        default=None,
        metavar="DOT_DEV_PATH",
        help="Seed test data from .dev file (default: auto-discover from project root)",
    )
    parser.add_argument(
        "--seed-from",
        type=str,
        default=None,
        metavar="ARCHIVE_PATH",
        help="Restore seed data from a .7z backup archive instead of generating from .dev",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind the server (default: LIGHTERBIRD_PORT env var or 8000)",
    )
    parser.add_argument(
        "--keep-data",
        action="store_true",
        help="Do not clean up the temp data directory on exit",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress informational output (errors still displayed)",
    )
    args = parser.parse_args()

    def _log(msg: str) -> None:
        if not args.quiet:
            print(msg)

    # Resolve port: CLI arg > LIGHTERBIRD_PORT env var > 8000
    port = args.port or int(os.environ.get("LIGHTERBIRD_PORT", 8000))

    # ── Create isolated data directory ───────────────────────────────────
    tmp_dir = Path(tempfile.mkdtemp(prefix="lighterbird-dev-"))
    data_dir = tmp_dir / "data"
    config_dir = tmp_dir / "config"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    # Set env vars BEFORE any lighterbird imports
    os.environ["LIGHTERBIRD_DATA_DIR"] = str(data_dir)
    os.environ["LIGHTERBIRD_CONFIG_DIR"] = str(config_dir)
    os.environ["LIGHTERBIRD_CACHE_DIR"] = str(tmp_dir / "cache")
    os.environ["LIGHTERBIRD_STATE_DIR"] = str(tmp_dir / "state")

    _log(f"[lighterbird-dev] Data dir: {data_dir}")
    _log(f"[lighterbird-dev] Config dir: {config_dir}")

    # ── Seed from archive ────────────────────────────────────────────────
    if args.seed_from:
        archive_path = Path(args.seed_from)
        if not archive_path.exists():
            print(f"[lighterbird-dev] ERROR: Seed archive not found: {archive_path}")
            raise SystemExit(1)

        _log(f"[lighterbird-dev] Restoring seed from: {archive_path}")
        from lighterbird.core.backup import _extract_archive

        extracted = _extract_archive(archive_path, data_dir)
        if extracted:
            _log(f"[lighterbird-dev] Restored {len(extracted)} file(s)")

        # Also try to restore config files
        config_restore_dir = data_dir / "config"
        if config_restore_dir.is_dir():
            for f in config_restore_dir.iterdir():
                dst = config_dir / f.name
                shutil.copy2(str(f), str(dst))
                _log(f"[lighterbird-dev] Restored config: {f.name}")

    # ── Seed from .dev ───────────────────────────────────────────────────
    elif args.seed is not None:
        if args.seed == "auto":
            dot_dev = _find_dot_dev()
            if dot_dev is None:
                print("[lighterbird-dev] WARNING: No .dev file found. Seeding skipped.")
                dot_dev = None
            else:
                _log(f"[lighterbird-dev] Using .dev file: {dot_dev}")
        else:
            dot_dev = Path(args.seed)
            if not dot_dev.exists():
                print(f"[lighterbird-dev] ERROR: .dev file not found: {dot_dev}")
                raise SystemExit(1)
            _log(f"[lighterbird-dev] Using .dev file: {dot_dev}")

        if dot_dev:
            from lighterbird.scripts.seed import seed_data_dir
            seed_data_dir(data_dir, dot_dev)
            _log("[lighterbird-dev] Seed data generated successfully.")

    # ── Start server ─────────────────────────────────────────────────────
    _log(f"[lighterbird-dev] Starting server on http://127.0.0.1:{port}")
    _log("[lighterbird-dev] Press Ctrl+C to stop.")

    import uvicorn

    try:
        uvicorn.run(
            "lighterbird.server.app:create_app",
            host="127.0.0.1",
            port=port,
            factory=True,
            reload=False,
        )
    finally:
        if not args.keep_data:
            _log(f"[lighterbird-dev] Cleaning up: {tmp_dir}")
            shutil.rmtree(tmp_dir, ignore_errors=True)
        else:
            _log(f"[lighterbird-dev] Data preserved at: {tmp_dir}")


if __name__ == "__main__":
    dev_main()
