"""Tests for server/cowrite/engine.py — co-writing engine, diffs, and LLM integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lighterbird.core.ai import ProviderConfig
from lighterbird.server.cowrite.engine import (
    _clean_llm_response,
    compute_diffs,
    cowrite,
)

# ── _clean_llm_response ──────────────────────────────────────────────────────


class TestCleanLlmResponse:
    """Parse and validate LLM JSON responses."""

    def test_valid_json_no_fences(self):
        raw = '{"subject": "Hello", "body": "World"}'
        result = _clean_llm_response(raw, {"subject", "body"})
        assert result == {"subject": "Hello", "body": "World"}

    def test_valid_json_with_markdown_fences(self):
        raw = '```json\n{"subject": "Hi", "body": "There"}\n```'
        result = _clean_llm_response(raw, {"subject", "body"})
        assert result == {"subject": "Hi", "body": "There"}

    def test_valid_json_with_triple_backtick_no_lang(self):
        raw = '```\n{"subject": "A", "body": "B"}\n```'
        result = _clean_llm_response(raw, {"subject", "body"})
        assert result == {"subject": "A", "body": "B"}

    def test_surrounding_text_stripped(self):
        raw = 'Here is the revised text:\n{"subject": "Rev", "body": "Body"}\n--- end'
        result = _clean_llm_response(raw, {"subject", "body"})
        assert result == {"subject": "Rev", "body": "Body"}

    def test_raises_value_error_on_malformed_json(self):
        raw = '{"subject": "broken'
        with pytest.raises(ValueError):
            _clean_llm_response(raw, {"subject"})

    def test_raises_value_error_on_missing_fields(self):
        raw = '{"subject": "Only Subject"}'
        with pytest.raises(ValueError, match="missing or empty field 'body'"):
            _clean_llm_response(raw, {"subject", "body"})

    def test_raises_value_error_on_empty_string_field(self):
        raw = '{"subject": "", "body": "Content"}'
        with pytest.raises(ValueError, match="missing or empty field 'subject'"):
            _clean_llm_response(raw, {"subject", "body"})

    def test_raises_value_error_on_none_field(self):
        raw = '{"subject": null, "body": "Content"}'
        with pytest.raises(ValueError, match="missing or empty field 'subject'"):
            _clean_llm_response(raw, {"subject", "body"})

    def test_empty_input_raises_error(self):
        with pytest.raises(ValueError):
            _clean_llm_response("", {"field"})


# ── compute_diffs ────────────────────────────────────────────────────────────


class TestComputeDiffs:
    """Character-level diff computation between original and revised text."""

    def test_no_changes(self):
        diffs = compute_diffs("Hello world", "Hello world")
        assert len(diffs) == 1
        assert diffs[0]["tag"] == "equal"

    def test_simple_replacement(self):
        diffs = compute_diffs("Hello world", "Hello there")
        # "Hello " is equal (6 chars), then portions of "world"→"there" with
        # "r" shared as an equal match. Verify the overall structure.
        assert diffs[0]["tag"] == "equal"
        assert diffs[0]["start_orig"] == 0
        assert diffs[0]["end_orig"] == 6
        # At least one replace operation exists
        replace_ops = [d for d in diffs if d["tag"] == "replace"]
        assert len(replace_ops) >= 1

    def test_insertion(self):
        diffs = compute_diffs("Hello", "Hello world")
        insert_ops = [d for d in diffs if d["tag"] == "insert"]
        assert len(insert_ops) >= 1
        assert insert_ops[0]["inserted"] == " world"

    def test_deletion(self):
        diffs = compute_diffs("Hello world", "Hello")
        delete_ops = [d for d in diffs if d["tag"] == "delete"]
        assert len(delete_ops) >= 1
        assert delete_ops[0]["deleted"] == " world"

    def test_complete_replacement(self):
        diffs = compute_diffs("Old text", "New text")
        replace_ops = [d for d in diffs if d["tag"] == "replace"]
        assert any(d["deleted"] and d["inserted"] for d in replace_ops)

    def test_empty_original(self):
        diffs = compute_diffs("", "New content")
        insert_ops = [d for d in diffs if d["tag"] == "insert"]
        assert any(d["inserted"] == "New content" for d in insert_ops)

    def test_empty_revised(self):
        diffs = compute_diffs("Old content", "")
        delete_ops = [d for d in diffs if d["tag"] == "delete"]
        assert any(d["deleted"] == "Old content" for d in delete_ops)

    def test_diffs_contain_position_info(self):
        diffs = compute_diffs("Hello world", "Hello there")
        replace_ops = [d for d in diffs if d["tag"] == "replace"]
        assert len(replace_ops) >= 1
        op = replace_ops[0]
        assert "start_orig" in op
        assert "end_orig" in op
        assert op["start_orig"] <= op["end_orig"]
        # First change starts at index 6 (after "Hello ")
        assert op["start_orig"] == 6


# ── cowrite (integration with mocked LLM) ────────────────────────────────────


class TestCowrite:
    """End-to-end cowrite flow with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_calls_provider_and_returns_edits(self):
        """Happy path: provider returns valid JSON → edits are computed."""
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.config = ProviderConfig(
            provider_type="openai",
            api_key="sk-test",
            model="gpt-4o",
        )

        mock_core = AsyncMock()
        mock_core.chat.return_value = (
            '{"subject": "Revised Subject", "body": "Revised body text here"}'
        )

        with (
            patch(
                "lighterbird.server.cowrite.engine.get_provider",
                return_value=mock_provider,
            ),
            patch(
                "lighterbird.server.cowrite.engine.load_cowrite_style",
                return_value="Be concise.",
            ),
            patch(
                "lighterbird.server.cowrite.engine._get_core_provider",
                return_value=mock_core,
            ),
        ):
            result = await cowrite(
                "email-send",
                {"subject": "Original Subject", "body": "Original body"},
                "make it formal",
            )

        assert "edits" in result
        assert "revised" in result
        assert "original" in result
        assert "session_id" in result
        assert result["revised"]["subject"] == "Revised Subject"
        assert result["revised"]["body"] == "Revised body text here"
        assert result["original"] == {
            "subject": "Original Subject",
            "body": "Original body",
        }
        # Verify that edits were computed for each field
        assert "subject" in result["edits"]
        assert "body" in result["edits"]
        assert len(result["edits"]["subject"]) > 0

    @pytest.mark.asyncio
    async def test_raises_error_when_provider_unavailable(self):
        """Provider not configured → RuntimeError."""
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = False

        with patch(
            "lighterbird.server.cowrite.engine.get_provider",
            return_value=mock_provider,
        ), pytest.raises(RuntimeError, match="LLM not configured"):
            await cowrite("email-send", {"subject": "Hi"}, "improve")

    @pytest.mark.asyncio
    async def test_raises_error_on_empty_llm_response(self):
        """Provider returns empty string → RuntimeError."""
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.config = ProviderConfig(api_key="sk-test")

        mock_core = AsyncMock()
        mock_core.chat.return_value = ""

        with (
            patch(
                "lighterbird.server.cowrite.engine.get_provider",
                return_value=mock_provider,
            ),
            patch(
                "lighterbird.server.cowrite.engine.load_cowrite_style",
                return_value=None,
            ),
            patch(
                "lighterbird.server.cowrite.engine._get_core_provider",
                return_value=mock_core,
            ),pytest.raises(RuntimeError, match="empty response")
        ):
            await cowrite("email-send", {"subject": "Hi"}, "improve")

    @pytest.mark.asyncio
    async def test_raises_on_invalid_json_response(self):
        """Provider returns malformed JSON → ValueError."""
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.config = ProviderConfig(api_key="sk-test")

        mock_core = AsyncMock()
        mock_core.chat.return_value = "not valid json at all"

        with (
            patch(
                "lighterbird.server.cowrite.engine.get_provider",
                return_value=mock_provider,
            ),
            patch(
                "lighterbird.server.cowrite.engine.load_cowrite_style",
                return_value=None,
            ),
            patch(
                "lighterbird.server.cowrite.engine._get_core_provider",
                return_value=mock_core,
            ),pytest.raises(ValueError)
        ):
            await cowrite("email-send", {"subject": "Hi"}, "improve")

    @pytest.mark.asyncio
    async def test_raises_on_llm_call_failure(self):
        """Core provider.chat() raises → RuntimeError."""
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.config = ProviderConfig(api_key="sk-test")

        mock_core = AsyncMock()
        mock_core.chat.side_effect = ConnectionError("API unreachable")

        with (
            patch(
                "lighterbird.server.cowrite.engine.get_provider",
                return_value=mock_provider,
            ),
            patch(
                "lighterbird.server.cowrite.engine.load_cowrite_style",
                return_value=None,
            ),
            patch(
                "lighterbird.server.cowrite.engine._get_core_provider",
                return_value=mock_core,
            ),pytest.raises(RuntimeError, match="LLM call failed")
        ):
            await cowrite("email-send", {"subject": "Hi"}, "improve")

    @pytest.mark.asyncio
    async def test_uses_context_mode_none(self):
        """context_mode='none' should skip gathering context."""
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.config = ProviderConfig(api_key="sk-test")

        mock_core = AsyncMock()
        mock_core.chat.return_value = '{"subject": "Revised", "body": "Body"}'

        with (
            patch(
                "lighterbird.server.cowrite.engine.get_provider",
                return_value=mock_provider,
            ),
            patch(
                "lighterbird.server.cowrite.engine.load_cowrite_style",
                return_value=None,
            ),
            patch(
                "lighterbird.server.cowrite.engine._get_core_provider",
                return_value=mock_core,
            ),
        ):
            result = await cowrite(
                "email-send",
                {"subject": "Original", "body": "Body text"},
                "improve",
                context_mode="none",
            )

        assert result["revised"]["subject"] == "Revised"

    @pytest.mark.asyncio
    async def test_missing_fields_in_response_raises_value_error(self):
        """Provider returns JSON missing a required field → ValueError."""
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.config = ProviderConfig(api_key="sk-test")

        mock_core = AsyncMock()
        # Only "subject" returned, "body" is missing
        mock_core.chat.return_value = '{"subject": "Revised Subject"}'

        with (
            patch(
                "lighterbird.server.cowrite.engine.get_provider",
                return_value=mock_provider,
            ),
            patch(
                "lighterbird.server.cowrite.engine.load_cowrite_style",
                return_value=None,
            ),
            patch(
                "lighterbird.server.cowrite.engine._get_core_provider",
                return_value=mock_core,
            ),pytest.raises(ValueError, match="missing or empty field 'body'")
        ):
            await cowrite(
                "email-send",
                {"subject": "Original", "body": "Original body"},
                "improve",
            )
