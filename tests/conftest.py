"""Shared test fixtures for lighterbird tests.

Tests that create databases should use ``tmp_path`` + monkeypatching
of ``lighterbird.core.paths.data_dir`` to avoid touching the real data
directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def tmp_data_dir(monkeypatch: Any, tmp_path: Path) -> Path:
    """Isolate data directory to a temporary path.

    All path resolution calls during the test will point to ``tmp_path``
    instead of the real XDG directory.
    """
    monkeypatch.setenv("LIGHTERBIRD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("LIGHTERBIRD_CACHE_DIR", str(tmp_path))
    return tmp_path
