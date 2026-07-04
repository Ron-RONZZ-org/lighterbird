"""Tests for lighterbird.core.cowrite_style — editable co-writing style guide.

Covers: cowrite_style_path, load_cowrite_style, auto-seed, OSError fallback.

Config directory isolation is provided by the root conftest's
autouse ``auto_isolate_data_dir`` fixture.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lighterbird.core.cowrite_style import (
    DEFAULT_COWRITE_STYLE,
    cowrite_style_path,
    load_cowrite_style,
)


class TestCowriteStyle:
    def test_cowrite_style_path(self):
        path = cowrite_style_path()
        assert path.endswith("cowrite_style.md")

    def test_auto_seeds_on_first_call(self):
        content = load_cowrite_style()
        assert content == DEFAULT_COWRITE_STYLE

    def test_returns_existing_content(self):
        # First call auto-seeds, second call returns same
        content = load_cowrite_style()
        assert content == DEFAULT_COWRITE_STYLE

    def test_returns_existing_empty_then_auto_seed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
        style_file = tmp_path / "cowrite_style.md"
        style_file.write_text("", encoding="utf-8")
        content = load_cowrite_style()
        assert content == DEFAULT_COWRITE_STYLE
        assert style_file.read_text(encoding="utf-8") == DEFAULT_COWRITE_STYLE

    def test_oserror_fallback_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
        os.chmod(tmp_path, 0o444)
        content = load_cowrite_style()
        assert content is None
        os.chmod(tmp_path, 0o755)

    def test_default_style_is_string(self):
        assert isinstance(DEFAULT_COWRITE_STYLE, str)
        assert len(DEFAULT_COWRITE_STYLE) > 50
