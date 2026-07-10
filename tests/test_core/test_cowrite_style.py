"""Tests for core/cowrite_style.py — cascade co-writing style loading.

Covers:
- General cowrite_style.md auto-seed and loading
- Per-domain files auto-seed and cascade (general + domain)
- ``cowrite_style_domain_path()`` returns correct paths
- Error handling (OSError, empty files, whitespace-only)

Note: ``DEFAULT_COWRITE_STYLE`` has a trailing newline from the triple-quoted
string; ``load_cowrite_style()`` strips content, so assertions compare against
the stripped version.
"""

from __future__ import annotations

from lighterbird.core.cowrite_style import (
    DEFAULT_COWRITE_STYLE,
    DEFAULT_COWRITE_STYLE_EMAIL,
    DEFAULT_COWRITE_STYLE_JOURNAL,
    DEFAULT_COWRITE_STYLE_LETTER,
    DEFAULT_COWRITE_STYLE_TODO,
    cowrite_style_domain_path,
    cowrite_style_path,
    load_cowrite_style,
)

_EXPECTED_GENERAL = DEFAULT_COWRITE_STYLE.strip()


class TestCowriteStylePath:
    def test_general_path(self):
        path = cowrite_style_path()
        assert isinstance(path, str)
        assert path.endswith("cowrite_style.md")

    def test_domain_path(self):
        path = cowrite_style_domain_path("email")
        assert isinstance(path, str)
        assert path.endswith("cowrite_style_email.md")

    def test_domain_path_letter(self):
        path = cowrite_style_domain_path("letter")
        assert path.endswith("cowrite_style_letter.md")


class TestLoadCowriteStyleGeneral:
    """Test the general cowrite_style.md loading (no form_type)."""

    def test_loads_default_on_first_run(self, tmp_path, monkeypatch):
        """When no file exists, default is written and returned."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        content = load_cowrite_style()
        assert content == _EXPECTED_GENERAL
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
        assert content == _EXPECTED_GENERAL

    def test_whitespace_only_file(self, tmp_path, monkeypatch):
        """Whitespace-only file is treated as first run."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        (tmp_path / "cowrite_style.md").write_text("   \n\n", encoding="utf-8")
        content = load_cowrite_style()
        assert content == _EXPECTED_GENERAL

    def test_oserror_on_read_returns_none(self, tmp_path, monkeypatch):
        """When read fails and write also fails, return None."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        style_file = tmp_path / "cowrite_style.md"
        style_file.write_text("content", encoding="utf-8")
        tmp_path.chmod(0o000)
        try:
            content = load_cowrite_style()
            assert content is None
        finally:
            tmp_path.chmod(0o755)

    def test_oserror_on_write_returns_none(self, tmp_path, monkeypatch):
        """When the default cannot be written, return None."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        tmp_path.chmod(0o444)
        content = load_cowrite_style()
        assert content is None
        tmp_path.chmod(0o755)


class TestCowriteStyleCascade:
    """Test the cascade model: general + per-domain files."""

    def test_email_domain_appended(self, tmp_path, monkeypatch):
        """When editing email, general + email style are combined."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        # Pre-seed general file
        (tmp_path / "cowrite_style.md").write_text("# General\n- Use active voice", encoding="utf-8")

        content = load_cowrite_style("email-send")
        assert "# General" in content
        assert "- Use active voice" in content
        assert DEFAULT_COWRITE_STYLE_EMAIL.strip() in content
        assert "## Domain-specific Guide" in content
        # Domain file should now exist (auto-seeded)
        assert (tmp_path / "cowrite_style_email.md").exists()

    def test_todo_domain_appended(self, tmp_path, monkeypatch):
        """todo-add loads general + todo styles."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        content = load_cowrite_style("todo-add")
        assert _EXPECTED_GENERAL in content
        assert DEFAULT_COWRITE_STYLE_TODO.strip() in content

    def test_journal_domain(self, tmp_path, monkeypatch):
        """journal-write loads general + journal styles."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        content = load_cowrite_style("journal-write")
        assert _EXPECTED_GENERAL in content
        assert DEFAULT_COWRITE_STYLE_JOURNAL.strip() in content

    def test_letter_domain(self, tmp_path, monkeypatch):
        """letter-send loads general + letter styles."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        content = load_cowrite_style("letter-send")
        assert _EXPECTED_GENERAL in content
        assert DEFAULT_COWRITE_STYLE_LETTER.strip() in content

    def test_unknown_form_type_falls_back_to_general(self, tmp_path, monkeypatch):
        """An unknown form_type only loads the general file."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        content = load_cowrite_style("unknown-form")
        assert content == _EXPECTED_GENERAL
        # No domain file should be created
        assert not (tmp_path / "cowrite_style_unknown-form.md").exists()

    def test_domain_without_general_works(self, tmp_path, monkeypatch):
        """If general file doesn't exist, domain file still loads."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        # Don't seed general, use a pre-seeded email file
        (tmp_path / "cowrite_style_email.md").write_text("# My email rules", encoding="utf-8")

        content = load_cowrite_style("email-send")
        assert "# My email rules" in content
        assert "## Domain-specific Guide" in content

    def test_no_form_type_only_general(self, tmp_path, monkeypatch):
        """Calling load_cowrite_style() without form_type only loads general."""
        monkeypatch.setattr(
            "lighterbird.core.cowrite_style.config_dir",
            lambda: tmp_path,
        )
        content = load_cowrite_style()
        assert content == _EXPECTED_GENERAL
        # No domain files should be created
        assert not (tmp_path / "cowrite_style_email.md").exists()
        assert not (tmp_path / "cowrite_style_todo.md").exists()
