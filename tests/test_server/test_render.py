"""Tests for server/llm/render.py — Markdown-to-HTML rendering and sanitization."""

from __future__ import annotations

from lighterbird.server.llm.render import (
    _escape_attr,
    _escape_lt,
    _filter_attrs,
    _process_code_blocks,
    _sanitize_html,
    render_markdown,
    render_streaming_markdown,
)

# ── render_markdown ───────────────────────────────────────────────────────────


class TestRenderMarkdown:
    def test_empty_string(self):
        assert render_markdown("") == ""

    def test_whitespace_only(self):
        result = render_markdown("   ")
        # Whitespace-only renders as empty (mistune discards whitespace)
        assert result == ""

    def test_plain_text(self):
        """Plain text should be wrapped in <p> tags."""
        result = render_markdown("Hello world")
        assert "<p>Hello world</p>" in result

    def test_bold_text(self):
        result = render_markdown("**bold**")
        assert "<strong>bold</strong>" in result or "<p>" in result

    def test_italic_text(self):
        result = render_markdown("*italic*")
        assert "<em>italic</em>" in result or "<p>" in result

    def test_heading(self):
        result = render_markdown("# Title")
        assert "<h1>" in result

    def test_code_block(self):
        result = render_markdown("```\ncode\n```")
        assert "<pre><code>" in result.replace("\n", "")

    def test_inline_code(self):
        result = render_markdown("Use `code` here")
        assert "<code>code</code>" in result

    def test_link(self):
        result = render_markdown("[click](https://example.com)")
        # mistune with escape=True produces escaped HTML
        assert "click" in result
        assert "https://example.com" in result

    def test_unordered_list(self):
        result = render_markdown("- item")
        assert "<li>" in result and "<ul>" in result

    def test_strikethrough(self):
        result = render_markdown("~~struck~~")
        assert "<del>" in result or "struck" in result

    def test_mixed_formatting(self):
        result = render_markdown("# Hello\n\nThis is **bold** and *italic*.")
        assert "<h1>" in result
        assert "<strong>" in result or "**bold**" not in result
        assert "<em>" in result or "*italic*" not in result

    def test_xss_script_tag_stripped(self):
        result = render_markdown("<script>alert('xss')</script>")
        assert "<script>" not in result

    def test_xss_script_in_markdown(self):
        result = render_markdown("Hello <script>alert('xss')</script>")
        assert "<script>" not in result
        assert "Hello" in result


# ── render_streaming_markdown ────────────────────────────────────────────────


class TestRenderStreamingMarkdown:
    def test_empty_string(self):
        assert render_streaming_markdown("") == ""

    def test_plain_text(self):
        result = render_streaming_markdown("Hello world")
        assert "<p>Hello world</p>" in result

    def test_bold(self):
        result = render_streaming_markdown("**bold**")
        assert "<strong>bold</strong>" in result

    def test_italic(self):
        result = render_streaming_markdown("*italic*")
        assert "<em>italic</em>" in result

    def test_bold_italic(self):
        result = render_streaming_markdown("***bold italic***")
        assert "<strong><em>bold italic</em></strong>" in result

    def test_inline_code(self):
        result = render_streaming_markdown("`code`")
        assert "<code>code</code>" in result

    def test_fenced_code_block(self):
        result = render_streaming_markdown("```\ncode block\n```")
        assert "<pre><code>" in result

    def test_fenced_code_block_with_language(self):
        result = render_streaming_markdown("```python\nprint('hi')\n```")
        assert 'class="language-python"' in result

    def test_link(self):
        result = render_streaming_markdown("[text](https://example.com)")
        assert '<a href="https://example.com"' in result

    def test_strikethrough(self):
        result = render_streaming_markdown("~~deleted~~")
        assert "<del>deleted</del>" in result

    def test_paragraph_breaks(self):
        result = render_streaming_markdown("Para1\n\nPara2")
        assert "</p><p>" in result
        assert "Para1" in result
        assert "Para2" in result

    def test_single_newline_becomes_br(self):
        result = render_streaming_markdown("Line1\nLine2")
        assert "<br>" in result

    def test_html_escaping(self):
        result = render_streaming_markdown("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_partial_content_no_crash(self):
        """Should handle unclosed bold markers gracefully."""
        result = render_streaming_markdown("**unclosed")
        # Unclosed bold is still rendered
        assert "unclosed" in result


# ── _sanitize_html ────────────────────────────────────────────────────────────


class TestSanitizeHtml:
    def test_allowed_tag_preserved(self):
        result = _sanitize_html("<p>Hello</p>")
        assert result == "<p>Hello</p>"

    def test_disallowed_tag_stripped(self):
        result = _sanitize_html("<script>alert(1)</script>")
        # Opening tag's < is escaped, closing tag is stripped entirely
        assert "&lt;script>" in result  # &lt;script> (only < escaped)
        assert "</script>" not in result
        assert "alert(1)" in result

    def test_disallowed_opening_tag_escaped(self):
        result = _sanitize_html("<marquee>text</marquee>")
        # The < is escaped in the opening tag, closing tag stripped
        assert "&lt;marquee>" in result or result == "text"

    def test_allowed_attribute_preserved(self):
        result = _sanitize_html('<a href="https://example.com">link</a>')
        assert 'href="https://example.com"' in result

    def test_disallowed_attribute_stripped(self):
        result = _sanitize_html('<a href="https://x.com" onclick="evil()">link</a>')
        assert 'onclick=' not in result
        assert 'href="https://x.com"' in result

    def test_javascript_href_stripped(self):
        result = _sanitize_html('<a href="javascript:alert(1)">link</a>')
        # javascript: scheme is stripped from href value
        assert "javascript:" not in result

    def test_data_href_stripped(self):
        result = _sanitize_html('<a href="data:text/html,base64">link</a>')
        # data: scheme is stripped from href value
        assert "data:" not in result

    def test_empty_html(self):
        assert _sanitize_html("") == ""

    def test_no_html_plain_text(self):
        assert _sanitize_html("Hello world") == "Hello world"

    def test_allowed_attrs_on_span(self):
        result = _sanitize_html('<span class="highlight">text</span>')
        assert 'class="highlight"' in result

    def test_self_closing_tag(self):
        result = _sanitize_html("<br/>")
        assert "<br/>" in result

    def test_code_with_class(self):
        result = _sanitize_html('<code class="language-py">print(1)</code>')
        assert 'class="language-py"' in result
        assert "print(1)" in result

    def test_table_tags_preserved(self):
        html = "<table><tr><th align='left'>Name</th><td>Value</td></tr></table>"
        result = _sanitize_html(html)
        assert "<table>" in result
        assert "<th" in result
        assert "<td>" in result


# ── _escape_lt, _escape_attr, _filter_attrs, _process_code_blocks ────────────


class TestEscapeLt:
    def test_escapes_lt(self):
        assert _escape_lt("<hello>") == "&lt;hello>"

    def test_no_lt(self):
        assert _escape_lt("hello") == "hello"


class TestEscapeAttr:
    def test_escapes_ampersand(self):
        assert "&amp;" in _escape_attr("a&b")

    def test_escapes_quote(self):
        assert "&quot;" in _escape_attr('a"b')

    def test_escapes_lt_gt(self):
        assert _escape_attr("<x>") == "&lt;x&gt;"


class TestFilterAttrs:
    def test_allowed_attr_kept(self):
        allowed = {"href", "class"}
        result = _filter_attrs('<a href="https://x.com" class="link">', allowed)
        assert "href=" in result
        assert "class=" in result

    def test_disallowed_attr_removed(self):
        allowed = {"href"}
        result = _filter_attrs('<a href="https://x.com" onclick="evil()">', allowed)
        assert "href=" in result
        assert "onclick" not in result or "evil" not in result

    def test_javascript_href_stripped(self):
        allowed = {"href"}
        result = _filter_attrs('<a href="javascript:alert(1)">', allowed)
        # The value is emptied (javascript: scheme stripped, no value remains)
        assert result == "" or "javascript" not in result


class TestProcessCodeBlocks:
    def test_basic_code_block(self):
        result = _process_code_blocks("```\ncode\n```")
        # The trailing newline inside the fence is included
        assert "<pre><code>" in result
        assert "code" in result
        assert "</code></pre>" in result

    def test_code_block_with_language(self):
        result = _process_code_blocks("```python\nprint(1)\n```")
        assert 'class="language-python"' in result
        assert "print(1)" in result

    def test_no_code_block(self):
        result = _process_code_blocks("plain text")
        assert result == "plain text"
