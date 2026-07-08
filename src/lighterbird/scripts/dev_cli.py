"""CLI entry point for ``lighterbird-dev`` — isolated dev server with seed data.

Usage::

    # Start isolated server with seed data from .dev (test credentials)
    uv run lighterbird-dev --seed

    # Start isolated server with seed data from .prod (real credentials)
    uv run lighterbird-dev --prod

    # Start isolated server with persistent data dir and .prod credentials
    uv run lighterbird-dev --data-dir ~/lighterbird-data --prod

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


def _find_dot_prod() -> Path | None:
    """Find the ``.prod`` file by walking up from the project root."""
    candidate = Path(__file__).resolve().parent.parent.parent.parent / ".prod"
    return candidate if candidate.exists() else None


def _is_seeded(data_dir: Path) -> bool:
    """Check if *data_dir* already has database files (i.e. was seeded before).

    Returns ``True`` if any ``*.db`` or ``*.sqlite`` file exists directly
    under *data_dir*.
    """
    if not data_dir.is_dir():
        return False
    return any(data_dir.iterdir())


def dev_main() -> None:
    """Run an isolated lighterbird development server.

    By default creates a temporary data directory (``/tmp/lighterbird-dev-*``)
    and optionally seeds it with test data before starting the server.

    Use ``--data-dir PATH`` to keep data persistent across restarts — the
    server will re-use the same data and config directories on subsequent
    runs.  Seeding (from ``--seed``, ``--prod``, or ``--seed-from``) only
    runs when the data directory is empty or does not yet exist.
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
        "--prod",
        nargs="?",
        const="auto",
        default=None,
        metavar="DOT_PROD_PATH",
        help="Seed production data from .prod file (default: auto-discover from project root). "
        "Mutually exclusive with --seed and --seed-from.",
    )
    parser.add_argument(
        "--seed-from",
        type=str,
        default=None,
        metavar="ARCHIVE_PATH",
        help="Restore seed data from a .7z backup archive instead of generating from .dev/.prod",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        metavar="DIR",
        help="Persistent data directory (replaces ephemeral temp dir). "
        "Data survives restarts; seeding runs only when the dir is empty.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind the server (default: LIGHTERBIRD_PORT env var or 6006)",
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

    # Validate mutual exclusivity
    enabled_flags = [k for k in ("seed", "prod", "seed_from") if getattr(args, k) is not None]
    if len(enabled_flags) > 1:
        print(
            f"[lighterbird-dev] ERROR: --{enabled_flags[0]}, --{enabled_flags[1]} "
            "are mutually exclusive. Use only one."
        )
        raise SystemExit(1)

    def _log(msg: str) -> None:
        if not args.quiet:
            print(msg)

    # Resolve port: CLI arg > LIGHTERBIRD_PORT env var > 6006
    port = args.port or int(os.environ.get("LIGHTERBIRD_PORT", 6006))

    # ── Determine data directory ─────────────────────────────────────────
    use_persistent = args.data_dir is not None

    if use_persistent:
        root_dir = Path(args.data_dir).expanduser().resolve()
        root_dir.mkdir(parents=True, exist_ok=True)
    else:
        root_dir = Path(tempfile.mkdtemp(prefix="lighterbird-dev-"))

    data_dir = root_dir / "data"
    config_dir = root_dir / "config"
    data_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    # Set env vars BEFORE any lighterbird imports
    os.environ["LIGHTERBIRD_DATA_DIR"] = str(data_dir)
    os.environ["LIGHTERBIRD_CONFIG_DIR"] = str(config_dir)
    os.environ["LIGHTERBIRD_CACHE_DIR"] = str(root_dir / "cache")
    os.environ["LIGHTERBIRD_STATE_DIR"] = str(root_dir / "state")

    _log(f"[lighterbird-dev] Data dir: {data_dir}")
    _log(f"[lighterbird-dev] Config dir: {config_dir}")

    already_seeded = _is_seeded(data_dir)

    # ── Seed from archive ────────────────────────────────────────────────
    if args.seed_from:
        if already_seeded:
            _log("[lighterbird-dev] Data dir already has content — skipping seed-from (use an empty dir to re-seed).")
        else:
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
        if already_seeded:
            _log("[lighterbird-dev] Data dir already has content — skipping seed (use an empty dir to re-seed).")
        else:
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

    # ── Seed from .prod ──────────────────────────────────────────────────
    elif args.prod is not None:
        if already_seeded:
            _log("[lighterbird-dev] Data dir already has content — skipping prod-seed (use an empty dir to re-seed).")
        else:
            if args.prod == "auto":
                dot_prod = _find_dot_prod()
                if dot_prod is None:
                    print("[lighterbird-dev] WARNING: No .prod file found. Seeding skipped.")
                    dot_prod = None
                else:
                    _log(f"[lighterbird-dev] Using .prod file: {dot_prod}")
            else:
                dot_prod = Path(args.prod)
                if not dot_prod.exists():
                    print(f"[lighterbird-dev] ERROR: .prod file not found: {dot_prod}")
                    raise SystemExit(1)
                _log(f"[lighterbird-dev] Using .prod file: {dot_prod}")

            if dot_prod:
                from lighterbird.scripts.seed import seed_data_dir
                seed_data_dir(data_dir, dot_prod)
                _log("[lighterbird-dev] Seed data generated successfully from .prod.")

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
        if not use_persistent and not args.keep_data:
            _log(f"[lighterbird-dev] Cleaning up: {root_dir}")
            shutil.rmtree(root_dir, ignore_errors=True)
        elif use_persistent:
            _log(f"[lighterbird-dev] Data preserved at: {root_dir}")
        else:
            _log(f"[lighterbird-dev] Data preserved at: {root_dir}")


if __name__ == "__main__":
    dev_main()
