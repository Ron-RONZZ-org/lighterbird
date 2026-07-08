"""Tests for server/render_utils.py — shared content-to-HTML conversion."""

from __future__ import annotations

from lighterbird.server.render_utils import convert_to_html


class TestConvertToHtml:
    """Tests for the shared convert_to_html utility function."""

    def test_empty_string(self):
        assert convert_to_html("", "markdown") == ""

    def test_html_passthrough(self):
        """HTML format returns content as-is."""
        html = "<p>Hello <strong>World</strong></p>"
        assert convert_to_html(html, "html") == html

    def test_markdown_bold(self):
        result = convert_to_html("**bold**", "markdown")
        assert "<strong>bold</strong>" in result

    def test_markdown_heading(self):
        result = convert_to_html("# Title", "markdown")
        assert "<h1>" in result
        assert "Title" in result

    def test_markdown_italic(self):
        result = convert_to_html("*italic*", "markdown")
        assert "<em>italic</em>" in result

    def test_markdown_code(self):
        result = convert_to_html("`code`", "markdown")
        assert "<code>code</code>" in result

    def test_markdown_link(self):
        result = convert_to_html("[text](https://x.com)", "markdown")
        assert '<a href="https://x.com">' in result

    def test_plain_text_wrapped(self):
        """Plain text format escapes HTML and wraps in <pre>."""
        result = convert_to_html("Hello <World>", "plain")
        assert "<pre>" in result
        assert "&lt;World&gt;" in result

    def test_plain_text_no_markdown(self):
        """Plain text should not interpret markdown."""
        result = convert_to_html("**bold**", "plain")
        assert "<strong>" not in result
        assert "<pre>" in result

    def test_markdown_paragraphs(self):
        result = convert_to_html("Para1\n\nPara2", "markdown")
        assert "<p>Para1</p>" in result or "Para1" in result
        assert "Para2" in result

    def test_markdown_strikethrough(self):
        result = convert_to_html("~~struck~~", "markdown")
        assert "struck" in result
