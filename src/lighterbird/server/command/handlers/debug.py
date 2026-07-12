"""Command handler for ``!debug`` — diagnostics and troubleshooting.

Registered paths:
    - debug.sync.log
"""

from __future__ import annotations

from typing import Any

from lighterbird.core.sync_logger import get_log_path, read_log_lines
from lighterbird.server.command.registry import command


@command("debug.sync.log",
         description="Show the most recent synchronization activity log")
def debug_sync_log(remaining: list[str], flags: dict[str, str]) -> dict[str, Any]:
    """!debug sync log [<lines>]

    Displays recent entries from the sync log file, which records IMAP
    and CalDAV sync activity (errors, warnings, successes).

    An optional integer argument limits the number of lines shown
    (default 50, max 500).

    The log file path is shown at the top — click it to copy to clipboard.
    """
    n = 50
    if remaining:
        try:
            n = int(remaining[0])
            n = max(1, min(n, 500))
        except ValueError:
            n = 50

    log_path = get_log_path()
    entries = read_log_lines(n)
    path_str = str(log_path) if log_path else "(not available)"

    return {
        "type": "status",
        "title": f"Sync Log (last {len(entries)} entries)",
        "data": {
            "log_path": path_str,
            "entries": entries,
            "count": len(entries),
        },
    }
