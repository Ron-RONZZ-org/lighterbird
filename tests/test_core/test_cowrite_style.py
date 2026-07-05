"""Tests for core/cowrite_style.py — Co-writing style guide loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from lighterbird.core.cowrite_style import (
    DEFAULT_COWRITE_STYLE,
    cowrite_style_path,
    load_cowrite_style,
)


class TestCowriteStylePath:
    def test_returns_string(self):
        path = cowrite_style_path()
        assert isinstance(path, str)
        assert path.endswith("cowrite_style.md")


class TestLoadCowriteStyle:
    def test_loads_default_on_first_run(self, tmp_path, monkeypatch):
        """When no file exists, default is written and returned."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        content = load_cowrite_style()
        assert content == DEFAULT_COWRITE_STYLE
        # File should exist now
        assert (tmp_path / "cowrite_style.md").exists()

    def test_reads_existing_file(self, tmp_path, monkeypatch):
        """When file exists with content, it's read and returned."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        existing = "Custom style content"
        (tmp_path / "cowrite_style.md").write_text(existing, encoding="utf-8")
        content = load_cowrite_style()
        assert content == existing

    def test_empty_file_seeds_default(self, tmp_path, monkeypatch):
        """When file exists but is empty, it's treated as first run."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "cowrite_style.md").write_text("", encoding="utf-8")
        content = load_cowrite_style()
        assert content == DEFAULT_COWRITE_STYLE

    def test_whitespace_only_file(self, tmp_path, monkeypatch):
        """Whitespace-only file is treated as first run."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "cowrite_style.md").write_text("   \n\n", encoding="utf-8")
        content = load_cowrite_style()
        assert content == DEFAULT_COWRITE_STYLE

    def test_oserror_on_read_returns_default(self, tmp_path, monkeypatch):
        """When file exists but read fails, seed default and return it."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        # Make the config dir non-readable so path.read_text fails
        # but the parent mkdir + write_text in load_cowrite_style also fails
        style_file = tmp_path / "cowrite_style.md"
        style_file.write_text("content", encoding="utf-8")
        tmp_path.chmod(0o000)
        try:
            content = load_cowrite_style()
            # When both read and write fail, returns None
            assert content is None
        finally:
            tmp_path.chmod(0o755)

    def test_oserror_on_write_returns_none(self, tmp_path, monkeypatch):
        """When the default cannot be written, return None."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        # Make the config dir non-writable
        tmp_path.chmod(0o444)
        content = load_cowrite_style()
        assert content is None
        tmp_path.chmod(0o755)  # cleanup
