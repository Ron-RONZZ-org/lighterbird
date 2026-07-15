#!/usr/bin/env bash
# lighterbird test runner — auto-detects git worktree context.
#
# In a worktree (e.g. ~/.local/share/opencode/worktree/lighterbird/<branch>/):
#   - Finds the main checkout's .venv  (e.g. ~/kodo/autish/lighterbird/.venv/)
#   - Sets PYTHONPATH=<worktree>/src to pick up the worktree's code
#   - Runs pytest via that .venv's python
#
# In the main checkout: runs python -m pytest directly (assumes .venv active).
#
# Usage:  ./scripts/test.sh [pytest-args...]
# Example:
#   ./scripts/test.sh tests/test_email/ -x -v -k "backlog or drain"

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if git -C "$ROOT" rev-parse --is-inside-work-tree 2>/dev/null | grep -q true; then
    # git-common-dir points to the main repo's .git directory
    GIT_COMMON_DIR=$(cd "$ROOT" && git rev-parse --git-common-dir 2>/dev/null)
    if [ -n "$GIT_COMMON_DIR" ]; then
        MAIN_DIR=$(cd "$GIT_COMMON_DIR/.." && pwd)
        VENV_PYTHON="$MAIN_DIR/.venv/bin/python"
        if [ -x "$VENV_PYTHON" ]; then
            echo "[test.sh] Worktree detected — using $MAIN_DIR/.venv" >&2
            PYTHONPATH="$ROOT/src" exec "$VENV_PYTHON" -m pytest "$@"
        fi
    fi
fi

# Fallback: direct invocation (assumes a compatible .venv is already active)
exec python -m pytest "$@"
