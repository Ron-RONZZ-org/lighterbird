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

    def test_markdown_single_newline_br(self):
        """Single newline in markdown produces <br> (nl2br)."""
        result = convert_to_html("Line1\nLine2\nLine3", "markdown")
        assert "<br>" in result, f"Expected <br> for single newlines, got: {result}"

    def test_markdown_mixed_newlines(self):
        """Single newlines within paragraph produce <br>, double newlines new paragraph."""
        result = convert_to_html("Line1\nLine2\n\nNewPara", "markdown")
        assert "Line1" in result
        assert "Line2" in result
        assert "NewPara" in result
        assert "<br>" in result, f"Expected <br> between Line1 and Line2, got: {result}"
        # Line1 and Line2 should be in the same paragraph, NewPara in a different one
        assert "</p>" in result

    def test_markdown_single_newline_in_paragraph(self):
        """Single newline after a heading still gets nl2br in following paragraph."""
        result = convert_to_html("# Title\nBody text\nMore text", "markdown")
        assert "<br>" in result, f"Expected <br> between Body text and More text, got: {result}"

    def test_plain_text_preserves_newlines(self):
        """Plain text wraps in <pre> which preserves all newlines."""
        result = convert_to_html("Line1\nLine2", "plain")
        assert "<pre>" in result
        assert "Line1\nLine2" in result or "Line1<br>" in result

    def test_markdown_strikethrough(self):
        result = convert_to_html("~~struck~~", "markdown")
        assert "struck" in result


class TestComposeEmailHtml:
    """Tests for the compose_email_html utility function."""

    def test_empty_body(self):
        from lighterbird.server.render_utils import compose_email_html
        result = compose_email_html("Subject", "", "markdown")
        assert "Subject" in result
        assert "<div class=" in result or "Subject" in result

    def test_full_document_wrapper(self):
        from lighterbird.server.render_utils import compose_email_html
        result = compose_email_html("Test", "Hello", "plain", full_document=True)
        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "</body>" in result
        assert "Hello" in result

    def test_inner_html_only(self):
        from lighterbird.server.render_utils import compose_email_html
        result = compose_email_html("Test", "Hello", "plain", full_document=False)
        assert "<!DOCTYPE html>" not in result
        assert "<html" not in result
        assert "Test" in result
        assert "Hello" in result

    def test_with_signature(self):
        from lighterbird.server.render_utils import compose_email_html
        result = compose_email_html("Subj", "Body", "markdown",
                                     signature_text="-- John", signature_format="plain")
        assert "Subject" in result or "Subj" in result
        assert "Body" in result
        assert "John" in result
        assert "signature" in result.lower() or "signature-separator" in result

    def test_with_attachments(self):
        from lighterbird.server.render_utils import compose_email_html
        attachments = [{"uuid": "abc-123", "filename": "report.pdf"}]
        result = compose_email_html("Subj", "Body", "plain",
                                     attachments=attachments,
                                     attachment_base_url="/api/v1/email/attachments/")
        assert "report.pdf" in result
        assert "/api/v1/email/attachments/abc-123/download" in result

    def test_markdown_body_converted(self):
        from lighterbird.server.render_utils import compose_email_html
        result = compose_email_html("Subj", "**bold**", "markdown")
        assert "<strong>bold</strong>" in result

    def test_html_body_passthrough(self):
        from lighterbird.server.render_utils import compose_email_html
        result = compose_email_html("Subj", "<p>Hello</p>", "html")
        assert "<p>Hello</p>" in result

    def test_subject_escaped(self):
        from lighterbird.server.render_utils import compose_email_html
        result = compose_email_html("<script>alert(1)</script>", "Body", "plain")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
