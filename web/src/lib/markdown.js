/**
 * Lightweight streaming-safe markdown renderer.
 *
 * Converts markdown to HTML. Designed to handle partial/incremental
 * content (mid-word, unclosed tags) gracefully.
 *
 * No dependencies — ~60 lines of vanilla JS.
 */

/**
 * Render a markdown string to safe HTML.
 * Can be called repeatedly with accumulated tokens for progressive display.
 *
 * @param {string} text — raw markdown (may be partial)
 * @returns {string} safe HTML
 */
export function renderMarkdown(text) {
  if (!text) return "";

  // 1. Escape HTML special chars (but protect existing HTML entities)
  let h = text
    .replace(/&(?!#?\w+;)/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // 2. Fenced code blocks (```lang\n...\n```)
  h = h.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const langAttr = lang ? ` class="language-${lang}"` : "";
    return `<pre><code${langAttr}>${code.trim()}</code></pre>`;
  });

  // 3. Inline code
  h = h.replace(/`([^`]+)`/g, "<code>$1</code>");

  // 4. Bold + italic ***
  h = h.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  // 5. Bold **
  h = h.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // 6. Italic *
  h = h.replace(/\*(.+?)\*/g, "<em>$1</em>");

  // 7. Strikethrough ~~
  h = h.replace(/~~(.+?)~~/g, "<del>$1</del>");

  // 8. Links [text](url)
  h = h.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>',
  );

  // 9. Headings (must be at start of line)
  h = h.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  h = h.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  h = h.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // 10. Blockquotes
  h = h.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");

  // 11. Unordered lists (- item)
  h = h.replace(/^- (.+)$/gm, "<li>$1</li>");
  h = h.replace(/(<li>.*<\/li>\n?)+/g, "<ul>$&</ul>");

  // 12. Ordered lists (1. item)
  h = h.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");
  // Don't re-wrap already-wrapped ul
  h = h.replace(
    /(?!<ul>)<li>(.*?)<\/li>(?:\n<li>(.*?)<\/li>)*/g,
    "<ol>$&</ol>",
  );

  // 13. Horizontal rules
  h = h.replace(/^---$/gm, "<hr>");

  // 14. Paragraphs: double newline breaks
  h = h.replace(/\n\s*\n/g, "</p><p>");
  // 15. Single newline → line break
  h = h.replace(/\n/g, "<br>");

  // Wrap in <p> if not already wrapped
  if (!h.startsWith("<")) {
    h = "<p>" + h + "</p>";
  }

  return h;
}
