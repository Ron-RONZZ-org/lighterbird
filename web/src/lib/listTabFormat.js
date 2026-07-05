/**
 * Formatting utilities for list tabs.
 * Pure functions — no Svelte runes needed.
 */

/**
 * Format an ISO date string for display in a list.
 * - Today: shows time only
 * - This year: shows month + day
 * - Older: shows full date
 */
export function formatListItemDate(iso) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso.slice(0, 10);
    const now = new Date();
    const opts = d.toDateString() === now.toDateString()
      ? { hour: "2-digit", minute: "2-digit" }
      : d.getFullYear() === now.getFullYear()
        ? { month: "short", day: "numeric" }
        : { year: "numeric", month: "short", day: "numeric" };
    return d.toLocaleDateString([], opts);
  } catch {
    return iso.slice(0, 10);
  }
}

/**
 * Focus trap for modal dialogs.
 * Wraps Tab/Shift+Tab within the container's focusable elements.
 *
 * @param {() => HTMLElement} getContainer — callback returning the dialog root
 * @param {(e: KeyboardEvent) => void} [onKeydown] — optional extra handler
 * @returns {(e: KeyboardEvent) => void} keydown handler to mount on the overlay
 */
export function createDialogTrap(getContainer, onKeydown) {
  const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

  return function trapKeydown(e) {
    if (e.key === "Tab") {
      const container = getContainer();
      if (!container) return;
      const focusable = container.querySelectorAll(FOCUSABLE);
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    if (onKeydown) onKeydown(e);
  };
}

/**
 * Truncate a string with ellipsis if it exceeds max length.
 */
export function truncate(s, max) {
  if (!s) return "";
  return s.length > max ? s.slice(0, max - 1) + "\u2026" : s;
}

/**
 * Sanitize a filename to only alphanumeric characters plus - and _.
 * Falls back to "export" if the result would be empty.
 *
 * @param {string} name — base name (without extension)
 * @param {string} [extension] — file extension including dot, e.g. ".md"
 * @param {number} [maxLen=64] — max length of the base part
 * @returns {string} sanitized filename with extension
 */
export function sanitizeFilename(name, extension = "", maxLen = 64) {
  if (!name) return `export${extension}`;
  const base = name.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, maxLen);
  return `${base || "export"}${extension}`;
}

function escHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/**
 * Open a print-friendly window with proper styling for letters/emails.
 *
 * Creates a clean document with white background, serif fonts, page margins,
 * header fields, and the body content. Automatically triggers the print dialog
 * after the document loads.
 *
 * @param {string} title — document title / subject line
 * @param {Array<{label:string, value:string}>} headers — header rows (From, To, Date, etc.)
 * @param {string} bodyHtml — HTML body content (or plain text wrapped in <pre>)
 */
export function openPrintWindow(title, headers, bodyHtml) {
  const win = window.open("", "_blank");
  if (!win) {
    alert("Print window was blocked. Please allow popups and try again.");
    return;
  }
  const headerRows = headers
    .filter((h) => h.value)
    .map((h) => `<div class="field"><span class="label">${escHtml(h.label)}</span><span class="value">${escHtml(h.value)}</span></div>`)
    .join("\n    ");
  win.document.write(`<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>${escHtml(title)}</title>
  <style>
    @page { margin: 2cm; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Georgia, 'Times New Roman', serif; font-size: 12pt; line-height: 1.6; color: #000; background: #fff; padding: 0; max-width: 21cm; }
    .header { margin-bottom: 1.5cm; border-bottom: 2px solid #333; padding-bottom: 0.5cm; }
    .header h1 { font-size: 18pt; margin-bottom: 0.3cm; line-height: 1.3; }
    .field { display: flex; gap: 0.5cm; padding: 0.08cm 0; font-size: 11pt; }
    .label { color: #555; min-width: 3cm; flex-shrink: 0; font-weight: 600; }
    .value { color: #000; word-break: break-word; }
    hr { border: none; border-top: 1px solid #ccc; margin: 0.5cm 0; }
    .body { font-size: 12pt; line-height: 1.8; white-space: pre-wrap; padding: 0.5cm 0; }
    .body iframe, .body img { max-width: 100%; }
    @media print {
      body { margin: 0; }
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>${escHtml(title)}</h1>
    ${headerRows}
  </div>
  <hr>
  <div class="body">${bodyHtml}</div>
  <script>
    window.onload = function () { setTimeout(function () { window.print(); }, 300); };
  <\/script>
</body>
</html>`);
  win.document.close();
}

/**
 * Open a print window with a proper physical letter layout (not email-style).
 *
 * Produces a traditional letter format with:
 *   - Sender block (top-right)
 *   - Recipient block (below, left-aligned)
 *   - Date (right-aligned below sender)
 *   - Subject line (Objet:)
 *   - Body text
 *
 * @param {string} subject — letter object/subject
 * @param {string} senderText — multi-line sender info
 * @param {string} recipientText — multi-line recipient info
 * @param {string} dateStr — date string
 * @param {string} bodyHtml — HTML body content
 */
export function openLetterPrintWindow(subject, senderText, recipientText, dateStr, bodyHtml) {
  const win = window.open("", "_blank");
  if (!win) {
    alert("Print window was blocked. Please allow popups and try again.");
    return;
  }

  const senderLines = (senderText || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const recipientLines = (recipientText || "").split("\n").map((l) => l.trim()).filter(Boolean);
  const dateLine = dateStr ? new Date(dateStr).toLocaleDateString("fr-FR", {
    day: "numeric", month: "long", year: "numeric",
  }) : "";

  win.document.write(`<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>${escHtml(subject)}</title>
  <style>
    @page { margin: 2.5cm 2cm; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Times New Roman', Times, serif;
      font-size: 12pt; line-height: 1.5; color: #000;
      background: #fff; padding: 0;
      max-width: 19cm; margin: 0 auto;
    }

    /* Sender block — top right */
    .sender { text-align: right; margin-bottom: 1.5cm; font-size: 11pt; }
    .sender .name { font-weight: 700; font-size: 12pt; }
    .sender .line { margin-top: 0.05cm; }

    /* Recipient block — below, left */
    .recipient { margin-bottom: 1cm; font-size: 11pt; }
    .recipient .attn { font-weight: 700; font-size: 11pt; margin-bottom: 0.1cm; }

    /* Date — below recipient, right */
    .date-row { text-align: right; margin-bottom: 0.8cm; font-size: 11pt; }

    /* Subject line */
    .subject { margin-bottom: 0.8cm; font-size: 12pt; }
    .subject .label { font-weight: 700; }

    /* Body */
    .body { font-size: 12pt; line-height: 1.8; text-align: justify; }
    .body p { margin-bottom: 0.3cm; text-indent: 0; }
    .body p:first-of-type { margin-top: 0; }

    /* Signature block */
    .signature { margin-top: 1.5cm; text-align: right; font-size: 11pt; }

    @media print {
      body { margin: 0; }
    }
  </style>
</head>
<body>
  <!-- Sender -->
  <div class="sender">
    ${senderLines.map((l, i) => i === 0 ? `<div class="name">${escHtml(l)}</div>` : `<div class="line">${escHtml(l)}</div>`).join("\n    ")}
  </div>

  <!-- Recipient -->
  <div class="recipient">
    <div class="attn">A l'attention de</div>
    ${recipientLines.map((l) => `<div class="line">${escHtml(l)}</div>`).join("\n    ")}
  </div>

  <!-- Date -->
  ${dateLine ? `<div class="date-row">${escHtml(dateLine)}</div>` : ""}

  <!-- Subject -->
  ${subject ? `<div class="subject"><span class="label">Objet\u00a0: </span>${escHtml(subject)}</div>` : ""}

  <!-- Body -->
  <div class="body">${bodyHtml}</div>

  <script>
    window.onload = function () { setTimeout(function () { window.print(); }, 300); };
  <\/script>
</body>
</html>`);
  win.document.close();
}

/**
 * Preview text: first line, stripped of markdown, truncated.
 */
export function preview(s, max = 60) {
  if (!s) return "";
  const firstLine = s.split("\n")[0].trim();
  return truncate(firstLine.replace(/[#*_~`>]/g, ""), max);
}
