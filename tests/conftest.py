"""Shared test fixtures for lighterbird tests.

Tests that create databases should use ``tmp_path`` + monkeypatching
of data directory env vars to avoid touching the real data directory.

E2E tests use the session-scoped ``e2e_server`` fixture which starts a
seeded lighterbird server on a dynamic port and manages its lifecycle.
"""

from __future__ import annotations

import glob
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

# ── E2E CLI options ─────────────────────────────────────────────────────────


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run E2E browser tests (requires Playwright + Node.js)",
    )
    parser.addoption(
        "--keep-e2e-data",
        action="store_true",
        default=False,
        help="Preserve E2E temp data directory after test run",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip E2E tests unless ``--e2e`` is passed."""
    if config.getoption("--e2e"):
        return
    skip_e2e = pytest.mark.skip(reason="use --e2e to run E2E tests")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)


# ── Playwright browser detection ────────────────────────────────────────────


def _detect_chromium_path() -> str | None:
    """Find Playwright's installed Chromium binary.

    Searches common Playwright cache locations, then falls back to
    system-installed Chromium.
    """
    home = str(Path.home())
    candidates = [
        *glob.glob(
            home
            + "/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"
        ),
        *glob.glob(
            home + "/.cache/ms-playwright/chromium-*/chrome-linux/chrome"
        ),
        os.environ.get("PLAYWRIGHT_CHROMIUM_PATH", ""),
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
        shutil.which("google-chrome") or "",
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


# ── E2E server fixture ─────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def e2e_server(request: pytest.FixtureRequest) -> Iterator[dict[str, Any]]:
    """Start a seeded lighterbird server on a dynamic port.

    Yields a dict with:
        url: str — base URL (e.g., ``http://127.0.0.1:34567``)
        port: int
        tmp_dir: Path — temp data directory
        chrome_path: str or None — detected Chromium path
        web_root: Path — web/ directory for Node resolution

    Teardown:
        - Terminates the uvicorn process
        - Removes the temp directory (unless ``--keep-e2e-data``)
    """
    # ── 1. Find free port ────────────────────────────────────────────────
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    # ── 2. Create isolated data directory ────────────────────────────────
    tmp_dir = Path(tempfile.mkdtemp(prefix="lighterbird-e2e-"))

    # ── 3. Seed data ─────────────────────────────────────────────────────
    env = os.environ.copy()
    env["LIGHTERBIRD_DATA_DIR"] = str(tmp_dir)
    env["LIGHTERBIRD_CONFIG_DIR"] = str(tmp_dir)
    env["LIGHTERBIRD_CACHE_DIR"] = str(tmp_dir)
    env["LIGHTERBIRD_STATE_DIR"] = str(tmp_dir)

    from lighterbird.scripts.seed import seed_data_dir
    seed_data_dir(tmp_dir)
    print(f"[e2e] Seeded data at: {tmp_dir}")

    # ── 4. Start uvicorn subprocess ──────────────────────────────────────
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "lighterbird.server.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    # ── 5. Health check (up to 15s) ──────────────────────────────────────
    health_url = f"{url}/api/v1/health"
    deadline = time.monotonic() + 15
    last_err = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as resp:
                if resp.status == 200:
                    print(f"[e2e] Server ready at {url}")
                    break
        except (urllib.error.URLError, OSError) as e:
            last_err = str(e)
        time.sleep(0.5)
    else:
        out = proc.communicate(timeout=5)[1]
        proc.kill()
        shutil.rmtree(tmp_dir, ignore_errors=True)
        pytest.fail(
            f"Server failed to start on port {port}\n"
            f"Last error: {last_err}\n"
            f"Server stderr:\n{out.decode(errors='replace')}"
        )

    # ── 6. Detect browser path ───────────────────────────────────────────
    chrome_path = _detect_chromium_path()
    if not chrome_path:
        proc.terminate()
        shutil.rmtree(tmp_dir, ignore_errors=True)
        pytest.fail(
            "No Chromium browser found for Playwright. "
            "Run: cd web && npx playwright install chromium"
        )

    yield {
        "url": url,
        "port": port,
        "tmp_dir": tmp_dir,
        "chrome_path": chrome_path,
    }

    # ── 7. Teardown ──────────────────────────────────────────────────────
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)

    if request.config.getoption("--keep-e2e-data"):
        print(f"[e2e] Data preserved at: {tmp_dir}")
    else:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"[e2e] Cleaned up: {tmp_dir}")


# ── Data isolation ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def auto_isolate_data_dir(
    tmp_path: Path, monkeypatch: Any, request: pytest.FixtureRequest,
) -> None:
    """Isolate EVERY test from the real data directory (autouse).

    All path resolution calls during the test will point to a unique
    ``tmp_path`` instead of the real XDG directory.  This prevents:

    * State pollution — tests that trigger ``get_email_service()`` via
      command handlers accidentally writing to ``~/.local/share/lighterbird/``.
    * Flaky ordering-dependent failures — the 4 ``test_server.py`` tests
      that failed only in the full suite because preceding tests left
      behind accounts/calendars in the real DB.

    Tests that genuinely need the real default path (e.g. ``test_data_dir_default``)
    can opt out with ``@pytest.mark.no_isolation``.
    """
    if request.node.get_closest_marker("no_isolation"):
        return

    from lighterbird.server.deps import reset_services as _reset_svc

    monkeypatch.setenv("LIGHTERBIRD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("LIGHTERBIRD_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("LIGHTERBIRD_STATE_DIR", str(tmp_path))
    _reset_svc()


@pytest.fixture
def tmp_data_dir(monkeypatch: Any, tmp_path: Path) -> Path:
    """Explicit opt-in data isolation (for tests that don't want autouse)."""
    monkeypatch.setenv("LIGHTERBIRD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("LIGHTERBIRD_CACHE_DIR", str(tmp_path))
    return tmp_path



