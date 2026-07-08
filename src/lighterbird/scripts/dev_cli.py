"""CLI entry point for ``lighterbird-dev`` — isolated dev server with seed data.

Uses ``lightercore.dev_helpers`` for shared dev-server infrastructure.

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

import os
import shutil
from pathlib import Path

from lightercore.dev_helpers import (
    cleanup_data_dir,
    find_dot_dev,
    find_dot_prod,
    is_seeded,
    setup_data_dir,
    standard_dev_parser,
    validate_seed_sources,
)


def dev_main() -> None:
    """Run an isolated lighterbird development server.

    By default creates a temporary data directory (``/tmp/lighterbird-dev-*``)
    and optionally seeds it with test data before starting the server.

    Use ``--data-dir PATH`` to keep data persistent across restarts — the
    server will re-use the same data and config directories on subsequent
    runs.  Seeding (from ``--seed``, ``--prod``, or ``--seed-from``) only
    runs when the data directory is empty or does not yet exist.
    """
    parser = standard_dev_parser(
        "Run an isolated lighterbird development server.",
        default_port=6006,
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind the server (default: LIGHTERBIRD_PORT env var or 6006)",
    )
    args = parser.parse_args()

    validate_seed_sources(args)

    LOG_PREFIX = "[lighterbird-dev]"

    def _log(msg: str) -> None:
        if not args.quiet:
            print(f"{LOG_PREFIX} {msg}")

    # Resolve port: CLI arg > LIGHTERBIRD_PORT env var > 6006
    port = args.port or int(os.environ.get("LIGHTERBIRD_PORT", 6006))

    # ── Setup data directory ──────────────────────────────────────────────
    root_dir, data_dir, config_dir, is_temp = setup_data_dir(
        args.data_dir, app_name="lighterbird",
    )

    _log(f"Data dir: {data_dir}")
    _log(f"Config dir: {config_dir}")

    already_seeded = is_seeded(data_dir)

    # ── Seed from archive ────────────────────────────────────────────────
    if args.seed_from:
        if already_seeded:
            _log("Data dir already has content — skipping seed-from (use an empty dir to re-seed).")
        else:
            archive_path = Path(args.seed_from)
            if not archive_path.exists():
                print(f"{LOG_PREFIX} ERROR: Seed archive not found: {archive_path}")
                raise SystemExit(1)

            _log(f"Restoring seed from: {archive_path}")
            from lighterbird.core.backup import _extract_archive

            extracted = _extract_archive(archive_path, data_dir)
            if extracted:
                _log(f"Restored {len(extracted)} file(s)")

            # Also try to restore config files
            config_restore_dir = data_dir / "config"
            if config_restore_dir.is_dir():
                for f in config_restore_dir.iterdir():
                    dst = config_dir / f.name
                    shutil.copy2(str(f), str(dst))
                    _log(f"Restored config: {f.name}")

    # ── Seed from .dev ───────────────────────────────────────────────────
    elif args.seed is not None:
        if already_seeded:
            _log("Data dir already has content — skipping seed (use an empty dir to re-seed).")
        else:
            if args.seed == "auto":
                dot_dev = find_dot_dev(__file__)
                if dot_dev is None:
                    print(f"{LOG_PREFIX} WARNING: No .dev file found. Seeding skipped.")
                    dot_dev = None
                else:
                    _log(f"Using .dev file: {dot_dev}")
            else:
                dot_dev = Path(args.seed)
                if not dot_dev.exists():
                    print(f"{LOG_PREFIX} ERROR: .dev file not found: {dot_dev}")
                    raise SystemExit(1)
                _log(f"Using .dev file: {dot_dev}")

            if dot_dev:
                from lighterbird.scripts.seed import seed_data_dir
                seed_data_dir(data_dir, dot_dev)
                _log("Seed data generated successfully.")

    # ── Seed from .prod ──────────────────────────────────────────────────
    elif args.prod is not None:
        if already_seeded:
            _log("Data dir already has content — skipping prod-seed (use an empty dir to re-seed).")
        else:
            if args.prod == "auto":
                dot_prod = find_dot_prod(__file__)
                if dot_prod is None:
                    print(f"{LOG_PREFIX} WARNING: No .prod file found. Seeding skipped.")
                    dot_prod = None
                else:
                    _log(f"Using .prod file: {dot_prod}")
            else:
                dot_prod = Path(args.prod)
                if not dot_prod.exists():
                    print(f"{LOG_PREFIX} ERROR: .prod file not found: {dot_prod}")
                    raise SystemExit(1)
                _log(f"Using .prod file: {dot_prod}")

            if dot_prod:
                from lighterbird.scripts.seed import seed_data_dir
                seed_data_dir(data_dir, dot_prod)
                _log("Seed data generated successfully from .prod.")

    # ── Start server ─────────────────────────────────────────────────────
    _log(f"Starting server on http://127.0.0.1:{port}")
    _log("Press Ctrl+C to stop.")

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
        cleanup_data_dir(
            root_dir, is_temp, args.keep_data,
            quiet=args.quiet, log_prefix=LOG_PREFIX,
        )


if __name__ == "__main__":
    dev_main()
