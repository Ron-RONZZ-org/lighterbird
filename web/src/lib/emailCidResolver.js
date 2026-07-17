/**
 * CID URL resolver for inline email images.
 *
 * Rewrites ``cid:`` references in HTML email bodies to our CID resolution
 * API route so embedded images render correctly in the sandboxed iframe.
 *
 * @param {string} htmlBody - The raw HTML body from the email
 * @param {string} messageUuid - The message UUID for building API URLs
 * @returns {string} HTML with ``cid:`` URLs rewritten to API paths
 */
export function resolveCidUrls(htmlBody, messageUuid) {
  if (!htmlBody || !messageUuid) return htmlBody || "";

  let h = htmlBody;

  // Rewrite src="cid:..." -> src="/api/v1/email/messages/{uuid}/cid/..."
  h = h.replace(
    /src=(["'])(?:cid:)([^"']+)\1/gi,
    (_, quote, cid) =>
      `src=${quote}/api/v1/email/messages/${messageUuid}/cid/${cid}${quote}`,
  );

  // Also handle src=cid:... without quotes (e.g. src=cid:logo@local>)
  // Captures the trailing delimiter so it is re-emitted (not consumed).
  h = h.replace(
    /\bsrc=(?:cid:)(\S+?)(\s|>)/gi,
    (_, cid, delim) =>
      `src="/api/v1/email/messages/${messageUuid}/cid/${cid}"${delim}`,
  );

  return h;
}
