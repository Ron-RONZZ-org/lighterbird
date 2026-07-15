# AGENTS-tests.md — Testing Guide for lighterbird

This file contains testing instructions extracted from the root `AGENTS.md`. Agents should follow these conventions when writing, running, or fixing tests.

---

## Running Tests from Git Worktrees

When running tests in a git worktree (created by `worktreeCreate` or `git worktree add`),
the worktree does **not** have its own `.venv` — it shares the main checkout's virtual
environment.  The project provides a convenience script that auto-detects this:

```bash
./scripts/test.sh [pytest-args...]
```

This script:
1. Detects if the current directory is inside a git worktree via
   `git rev-parse --is-inside-work-tree`.
2. If yes, finds the **main checkout's** `.venv` via `git rev-parse --git-common-dir`
   and uses that Python interpreter, with `PYTHONPATH=<worktree-root>/src` to pick up
   the worktree's code (the main checkout's editable install `.pth` file still points
   to the parent `src/`, so `PYTHONPATH` must override it).
3. If in the main checkout, runs `python -m pytest` directly (assumes `.venv` is active).

**Example** — run only email-anchored tests from a worktree:
```bash
./scripts/test.sh tests/test_email/ -x -v
```

**Manual invocation** (equivalent to what the script does for a worktree):
```bash
PYTHONPATH=src /path/to/main/checkout/.venv/bin/python -m pytest tests/...
```

---

## Dev Instance for Realistic Testing

When working on lighterbird, **always spring up a seeded dev instance** for any testing beyond trivial unit-test changes. This gives you a real server with real accounts to test against.

```bash
# Quick dev instance (ephemeral — data lost on exit)
uv run lighterbird-dev --seed --port 6006

# Dev instance with persistent data (survives restarts)
uv run lighterbird-dev --data-dir ~/lighterbird-data --seed --port 6006

# Dev instance with your real credentials
uv run lighterbird-dev --data-dir ~/lighterbird-data --prod --port 6006
```

E2E tests (Playwright) start their own seeded instance automatically — see **E2E Test Automation** below. The above is for manual exploration or API-level testing.

---

## Testing Requirements

**Full test suite timeout**: Running `uv run pytest tests/` takes ~5+ minutes (427 email tests, plus calendar, contacts, todo, journal, server, core, and more). In practice it's been observed to exceed 7 minutes, so set a shell timeout of at least 600000ms (10 minutes). Unless you have specific reason to suspect wide-ranging breakage, run only tests relevant to your changes.

### GUI + Incomplete CLI → GUI Form Testing

**All interactive commands MUST be tested via BOTH the API and the browser GUI.** Incomplete CLI commands that trigger a form popup (`form-required` response) are the primary UX pattern and must be explicitly verified end-to-end:

1. **Test incomplete commands that trigger form popups** — for every command with `interactive: true` in `tree.py`:
   - Type the command with missing required params (e.g. `!user info add` without a profile name)
   - Verify the GUI opens the correct form with all fields visible
   - Verify the form title matches the command
   - Verify the "Save" button submits correctly
   - Verify the result tab shows success

2. **Test the frontend interception (`shouldIntercept` in `commandRouter.js`)** — for every `add`/`write` command:
   - Verify `resolveAddFormType()` has a mapping for the command path
   - Verify `resolveListIdKey()` has a mapping for the list command path
   - Verify `resolveAddTitle()` has a title for the form type
   - Verify `_inferCommandPath()` in `FormTab.svelte` has the form type → command path mapping
   - If any of these mappings are missing, the form shows "Unknown form type" instead of the correct form.

3. **The authoritative list of mappings to check** — when adding a new interactive command, update ALL of these:
   - `_INTERACTIVE_FORMS` in `server/command/handlers/__init__.py` (backend)
   - `resolveAddFormType()` in `web/src/lib/commandRouter.js`
   - `resolveListIdKey()` in `web/src/lib/commandRouter.js`
   - `resolveAddTitle()` in `web/src/lib/commandRouter.js`
   - `_inferCommandPath()` in `web/src/lib/FormTab.svelte`
   - `detectPersistentType()` in `web/src/App.svelte` and `web/src/lib/HomeTab.svelte`

4. **GUI tests use headless Playwright — ALWAYS prefer E2E scripts over the interactive browser tool.**
   - **One-time setup**: Ensure Playwright's Chromium is installed before running E2E tests:
     ```bash
     cd web && npx playwright install chromium
     ```
     Without this, the E2E fixture fails with "No Chromium browser found". The download is ~300MB and takes ~90s.
   - **Run the E2E test scripts (`node tests/e2e_comprehensive.mjs`, `node tests/playwright_e2e.mjs`)** as the primary verification method. These are fast, reliable, and catch regressions automatically.
   - **Use the `browser` tool (headed mode) ONLY as a last resort** when an E2E script cannot reproduce the issue and you need to manually inspect the UI. Headed mode sessions are fragile: tool calls are interrupted if the user types "continue" while an action is in-flight, leaving the browser in an inconsistent state.
   - Always use `http://127.0.0.1:<port>` for local dev servers (IPv4, not `localhost` which can resolve to IPv6 `::1`).
   - **Timeout**: E2E tests take ~2 minutes. When running via the shell tool, set a timeout of at least 300s (`timeout: 300000`).

5. **Use `lighterbird-dev --seed` for isolated E2E testing** — instead of starting the production server, use the isolated dev server which creates a temporary data directory and seeds it with test data from ``.dev``:

   **Always use a dynamically-allocated free port.** Never kill a process on the default port (6006) — it may belong to the user's manual dev instance. Find a free port first:

   ```bash
   # Find a free TCP port (never kill a foreign process on the default port)
   PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()")

   # Start isolated seeded server on that port
   setsid uv run lighterbird-dev --seed --port $PORT > /tmp/lighterbird-dev.log 2>&1 &

   # Wait for server to accept connections
   for i in $(seq 1 30); do
     curl -sf -o /dev/null http://127.0.0.1:$PORT/ && break
     sleep 1
   done

   # Run Playwright E2E tests against that port
   # (one-time setup: cd web && npx playwright install chromium)
   node tests/playwright_e2e.mjs
   node tests/e2e_comprehensive.mjs
   ```

   The seeded data includes an email account (from ``.dev`` credentials with auto-detected IMAP/SMTP), a calendar account with a sample event, a test contact, sample todos, a journal entry, and a user profile. See ``scripts/AGENTS-scripts.md`` for details.

6. **Cowriting via GUI** — test LLM co-writing through form editors (ComposeEmail, TodoAddForm, JournalWrite) by filling in text and invoking the cowrite feature. Also test via the cowrite API directly (`POST /api/v1/cowrite`).

### E2E Test Automation

Playwright E2E tests are integrated into pytest via the ``--e2e`` flag:

| Command | Behavior |
|---------|----------|
| `uv run pytest tests/` | Unit tests only (1379 tests, E2E skipped) |
| `uv run pytest --e2e tests/test_e2e.py` | E2E tests only (auto-starts seeded server) |
| `uv run pytest --e2e --keep-e2e-data` | E2E + preserve temp data for debugging |

**Prerequisite**: Playwright's Chromium must be installed:
```bash
cd web && npx playwright install chromium
```

The ``conftest.py`` defines a session-scoped ``e2e_server`` fixture that:
1. Allocates a free TCP port (no port conflicts)
2. Creates a temp data directory and seeds it
3. Starts uvicorn as a subprocess
4. Health-checks before proceeding (15s timeout)
5. Yields URL + Chromium path to the test
6. Terminates server + cleans up temp dir on teardown

Existing ``.mjs`` scripts (``tests/playwright_e2e.mjs``, ``tests/e2e_comprehensive.mjs``) are wrapped by ``tests/test_e2e.py`` via ``subprocess.run()`` — no script rewrite needed.
