"""Tests for core/cowrite_style.py — style guide loading and seeding."""

from __future__ import annotations

from pathlib import Path

from lighterbird.core.cowrite_style import (
    DEFAULT_COWRITE_STYLE,
    cowrite_style_path,
    load_cowrite_style,
)


def test_default_style_is_nonempty():
    assert len(DEFAULT_COWRITE_STYLE) > 100
    assert "Tone" in DEFAULT_COWRITE_STYLE


def test_cowrite_style_path_ends_with_correct_filename():
    path = cowrite_style_path()
    assert path.endswith("cowrite_style.md")


def test_load_cowrite_style_seeds_on_first_call(monkeypatch, tmp_path):
    """On first call with no existing file, the shipped default is written."""
    monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
    content = load_cowrite_style()
    assert content == DEFAULT_COWRITE_STYLE
    # File should now exist on disk
    expected_file = tmp_path / "cowrite_style.md"
    assert expected_file.exists()
    assert expected_file.read_text(encoding="utf-8") == DEFAULT_COWRITE_STYLE


def test_load_cowrite_style_returns_existing_content(monkeypatch, tmp_path):
    """If the file already exists, return its content unchanged."""
    monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
    custom_content = "My custom style guide"
    custom_file = tmp_path / "cowrite_style.md"
    custom_file.parent.mkdir(parents=True, exist_ok=True)
    custom_file.write_text(custom_content, encoding="utf-8")

    result = load_cowrite_style()
    assert result == custom_content


def test_load_cowrite_style_empty_file_triggers_reseed(monkeypatch, tmp_path):
    """If the file exists but is empty, reseed with default."""
    monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
    custom_file = tmp_path / "cowrite_style.md"
    custom_file.parent.mkdir(parents=True, exist_ok=True)
    custom_file.write_text("   ", encoding="utf-8")  # whitespace-only

    result = load_cowrite_style()
    assert result == DEFAULT_COWRITE_STYLE


def test_cowrite_style_path_respects_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
    path = Path(cowrite_style_path())
    assert path.parent == tmp_path
