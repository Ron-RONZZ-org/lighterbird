<script>
  let { data = {} } = $props();
  let msg = $derived(data);

  /** Strip HTML tags and decode common entities for plain-text display. */
  function stripHtml(html) {
    const text = html.replace(/<[^>]*>/g, "");
    return text
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .replace(/&nbsp;/g, " ")
      .replace(/&#?\w+;/g, "")  // remove any remaining entities
      .trim();
  }

  let displayBody = $derived(msg.body || (msg.html_body ? stripHtml(msg.html_body) : "(no body)"));
</script>

<div class="email">
  <div class="field">
    <span class="label">From</span>
    <span class="value">{msg.from || ""}</span>
  </div>
  <div class="field">
    <span class="label">To</span>
    <span class="value">
      {Array.isArray(msg.to) ? msg.to.join(", ") : msg.to || ""}
    </span>
  </div>
  <div class="field">
    <span class="label">Subject</span>
    <span class="value subject">{msg.subject || "(no subject)"}</span>
  </div>
  <div class="field">
    <span class="label">Date</span>
    <span class="value">{msg.received_at || ""}</span>
  </div>
  <div class="field">
    <span class="label">Read</span>
    <span class="value">{msg.is_read ? "yes" : "no"}</span>
  </div>
  <hr />
  <div class="body-text">{displayBody}</div>
</div>

<style>
  .email {
    font-family: system-ui, monospace;
    font-size: 0.9rem;
  }
  .field {
    display: flex;
    gap: 0.5rem;
    padding: 0.2rem 0;
  }
  .label {
    color: #7c7c9a;
    min-width: 5rem;
    flex-shrink: 0;
  }
  .value {
    color: #e0e0e0;
  }
  .subject {
    font-weight: 600;
  }
  hr {
    border: none;
    border-top: 1px solid #333;
    margin: 0.75rem 0;
  }
  .body-text {
    color: #ccc;
    white-space: pre-wrap;
    line-height: 1.5;
    max-height: 40vh;
    overflow-y: auto;
  }
</style>
