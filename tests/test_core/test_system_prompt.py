"""Tests for lighterbird.core.system_prompt — editable system prompt.

Covers: system_prompt_path, load_system_prompt, reload_system_prompt,
auto-seed, OSError fallback.

Config directory isolation is provided by the root conftest's
autouse ``auto_isolate_data_dir`` fixture.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from lighterbird.core.system_prompt import (
    DEFAULT_SYSTEM_PROMPT,
    load_system_prompt,
    reload_system_prompt,
    system_prompt_path,
)


# The DEFAULT_SYSTEM_PROMPT has a trailing newline from the triple-quoted
# string; SystemPromptManager.load() strips whitespace, so we strip here too.
_EXPECTED = DEFAULT_SYSTEM_PROMPT.strip()


class TestSystemPromptPath:
    def test_path_ends_correctly(self):
        path = system_prompt_path()
        assert path.name == "system_prompt.md"


class TestLoadSystemPrompt:
    def test_auto_seeds_on_first_call(self):
        content = load_system_prompt()
        assert content == _EXPECTED

    def test_returns_existing_content(self):
        content = load_system_prompt()
        assert content == _EXPECTED

    def test_existing_empty_then_auto_seed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
        prompt_file = tmp_path / "system_prompt.md"
        prompt_file.write_text("", encoding="utf-8")
        content = load_system_prompt()
        assert content == _EXPECTED
        assert prompt_file.read_text(encoding="utf-8") == DEFAULT_SYSTEM_PROMPT

    def test_oserror_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
        os.chmod(tmp_path, 0o444)
        content = load_system_prompt()
        assert content == _EXPECTED
        os.chmod(tmp_path, 0o755)


class TestReloadSystemPrompt:
    def test_reload_returns_prompt(self):
        content = reload_system_prompt()
        assert content == _EXPECTED

    def test_reload_reflects_edits(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("LIGHTERBIRD_CONFIG_DIR", str(tmp_path))
        load_system_prompt()
        (tmp_path / "system_prompt.md").write_text("Edited prompt", encoding="utf-8")
        content = reload_system_prompt()
        assert content == "Edited prompt"

    def test_default_prompt_is_string(self):
        assert isinstance(DEFAULT_SYSTEM_PROMPT, str)
        assert "lighterbird" in DEFAULT_SYSTEM_PROMPT
