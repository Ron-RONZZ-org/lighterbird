"""Dedicated sync log file — captures IMAP and CalDAV sync activity."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from lighterbird.core.paths import data_dir

logger = logging.getLogger(__name__)

_SYNC_LOG_FILENAME = "sync.log"
_SYNC_LOGGER_NAMESPACES = (
    "lighterbird.email.imap",
    "lighterbird.email.service",
    "lighterbird.calendar",
)

_handler: logging.FileHandler | None = None
_log_path: Path | None = None


def init_sync_logger() -> Path:
    global _handler, _log_path
    _log_path = data_dir() / _SYNC_LOG_FILENAME
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    finalize()
    _handler = logging.FileHandler(str(_log_path), mode="w", encoding="utf-8")
    _handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _handler.setFormatter(fmt)
    for ns in _SYNC_LOGGER_NAMESPACES:
        ns_logger = logging.getLogger(ns)
        ns_logger.addHandler(_handler)
        # Force DEBUG level so all messages reach the handler —
        # parent loggers default to WARNING which would filter them out.
        ns_logger.setLevel(logging.DEBUG)
    logger.info("Sync log initialized: %s", _log_path)
    return _log_path


def finalize() -> None:
    global _handler
    if _handler is None:
        return
    try:
        for ns in _SYNC_LOGGER_NAMESPACES:
            logging.getLogger(ns).removeHandler(_handler)
        _handler.close()
    except Exception:
        pass
    _handler = None


def get_log_path() -> Path | None:
    return _log_path


def read_log_lines(n: int = 100) -> list[str]:
    path = _log_path
    if not path or not path.exists():
        return ["(sync log not available)"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [l.rstrip("\n") for l in lines[-n:]][::-1]
    except OSError as e:
        return [f"(error reading sync log: {e})"]
