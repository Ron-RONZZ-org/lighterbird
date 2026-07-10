"""Tests for core/config_defaults.py — startup seeding of default config files.

Covers:
- :func:`seed_config_defaults` creates missing files (system_prompt.md, cowrite_style.md)
- :func:`seed_config_defaults` does NOT overwrite existing files
- :func:`seed_config_defaults` handles empty files (reseed)
- :func:`seed_config_defaults` tolerates file-system errors gracefully
- The function is idempotent
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lighterbird.core.config_defaults import seed_config_defaults
from lighterbird.core.system_prompt import DEFAULT_SYSTEM_PROMPT
from lighterbird.core.cowrite_style import DEFAULT_COWRITE_STYLE


class TestSeedConfigDefaults:
    """Test the generalized startup seeding of default config files."""

    # The root conftest's auto_isolate_data_dir fixture sets
    # LIGHTERBIRD_CONFIG_DIR to tmp_path automatically.

    def test_creates_system_prompt(self, tmp_path: Path):
        """seed_config_defaults creates system_prompt.md when it doesn't exist."""
        assert not (tmp_path / "system_prompt.md").exists()

        seed_config_defaults()

        assert (tmp_path / "system_prompt.md").exists()
        content = (tmp_path / "system_prompt.md").read_text(encoding="utf-8").strip()
        assert content == DEFAULT_SYSTEM_PROMPT.strip()

    def test_creates_cowrite_style(self, tmp_path: Path):
        """seed_config_defaults creates cowrite_style.md when it doesn't exist."""
        assert not (tmp_path / "cowrite_style.md").exists()

        seed_config_defaults()

        assert (tmp_path / "cowrite_style.md").exists()
        content = (tmp_path / "cowrite_style.md").read_text(encoding="utf-8").strip()
        assert content == DEFAULT_COWRITE_STYLE.strip()

    def test_creates_both_files(self, tmp_path: Path):
        """Both config files are created in a single call."""
        seed_config_defaults()
        assert (tmp_path / "system_prompt.md").exists()
        assert (tmp_path / "cowrite_style.md").exists()

    def test_does_not_overwrite_system_prompt(self, tmp_path: Path):
        """An existing system_prompt.md is left untouched."""
        custom = "Custom prompt content."
        (tmp_path / "system_prompt.md").write_text(custom, encoding="utf-8")

        seed_config_defaults()

        assert (tmp_path / "system_prompt.md").read_text(encoding="utf-8") == custom

    def test_does_not_overwrite_cowrite_style(self, tmp_path: Path):
        """An existing cowrite_style.md is left untouched."""
        custom = "Custom style content."
        (tmp_path / "cowrite_style.md").write_text(custom, encoding="utf-8")

        seed_config_defaults()

        assert (tmp_path / "cowrite_style.md").read_text(encoding="utf-8") == custom

    def test_empty_file_is_reseeded(self, tmp_path: Path):
        """An empty file is reseeded with the shipped default."""
        (tmp_path / "system_prompt.md").write_text("", encoding="utf-8")
        (tmp_path / "cowrite_style.md").write_text("", encoding="utf-8")

        seed_config_defaults()

        sp_content = (tmp_path / "system_prompt.md").read_text(encoding="utf-8").strip()
        assert sp_content == DEFAULT_SYSTEM_PROMPT.strip()
        cs_content = (tmp_path / "cowrite_style.md").read_text(encoding="utf-8").strip()
        assert cs_content == DEFAULT_COWRITE_STYLE.strip()

    def test_whitespace_only_file_is_reseeded(self, tmp_path: Path):
        """A whitespace-only file is treated as empty and reseeded."""
        (tmp_path / "system_prompt.md").write_text("   \n\n  ", encoding="utf-8")

        seed_config_defaults()

        content = (tmp_path / "system_prompt.md").read_text(encoding="utf-8").strip()
        assert content == DEFAULT_SYSTEM_PROMPT.strip()

    def test_idempotent(self, tmp_path: Path):
        """Calling seed_config_defaults multiple times is safe."""
        seed_config_defaults()
        seed_config_defaults()
        seed_config_defaults()

        sp = (tmp_path / "system_prompt.md").read_text(encoding="utf-8").strip()
        assert sp == DEFAULT_SYSTEM_PROMPT.strip()
        cs = (tmp_path / "cowrite_style.md").read_text(encoding="utf-8").strip()
        assert cs == DEFAULT_COWRITE_STYLE.strip()

    def test_unreadable_file_logged_not_crashed(self, tmp_path: Path):
        """A permission-denied file does not crash seed_config_defaults."""
        prompt_file = tmp_path / "system_prompt.md"
        prompt_file.write_text("test", encoding="utf-8")
        prompt_file.chmod(0o000)
        try:
            seed_config_defaults()  # should not raise
        finally:
            prompt_file.chmod(0o644)  # restore for cleanup

    def test_non_existent_directory_created(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """If the config directory doesn't exist, it is created."""
        nested = tmp_path / "nonexistent" / "subdir"
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(nested))

        seed_config_defaults()

        assert nested.exists()
        assert (nested / "system_prompt.md").exists()
