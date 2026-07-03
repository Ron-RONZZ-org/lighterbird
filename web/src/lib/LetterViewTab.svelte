<script>
  import { tabStore } from "./tabStore.svelte.js";

  let { data = {} } = $props();
  let letter = $derived(data?.letter || {});
  let body = $derived(data?.body || "");

  function handleKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "p") {
      e.preventDefault();
      printLetter();
    }
  }

  function respond() {
    tabStore.open("form", "Send Letter", { form: "letter-send", initialData: {
      "respond-to": letter.uuid,
      object: letter.object ? `Re: ${letter.object}` : "",
      _returnIdKey: "persistent-letter-list",
      _returnType: "letter-list",
      _returnTitle: "Letters",
    } }, {
      idKey: "letter-send",
    });
  }

  function printLetter() {
    window.print();
  }

  async function exportMarkdown() {
    if (!letter.uuid) return;
    try {
      const res = await fetch(`/api/v1/letters/export-md/${letter.uuid}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      const blob = new Blob([text], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${letter.object || "letter"}.md`.replace(/[^a-zA-Z0-9._ -]/g, "_");
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Export markdown failed", err);
    }
  }

  function senderDisplay() {
    if (letter.sender_manual) return letter.sender_manual;
    return letter.sender_profile ? `Profile: ${letter.sender_profile.slice(0, 8)}` : "—";
  }

  function recipientDisplay() {
    if (letter.recipient_manual) return letter.recipient_manual;
    return letter.recipient_contact ? `Contact: ${letter.recipient_contact.slice(0, 8)}` : "—";
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="letter-view">
  <div class="toolbar">
    <button class="tool-btn" onclick={respond} title="Respond to this letter">Respond ↩</button>
    <button class="tool-btn" onclick={printLetter} title="Print (Ctrl+P)"><kbd>Ctrl+P</kbd> Print</button>
    <button class="tool-btn" onclick={exportMarkdown} title="Export as Markdown">Export .md</button>
    <div class="toolbar-spacer"></div>
    {#if letter.respond_to_uuid}
      <span class="meta-info">In reply to: {letter.respond_to_uuid.slice(0, 8)}</span>
    {/if}
  </div>

  <div class="headers">
    <div class="field">
      <span class="label">Direction</span>
      <span class="value">{letter.direction === "sent" ? "✉ Sent" : "📥 Received"}</span>
    </div>
    <div class="field">
      <span class="label">Sender</span>
      <span class="value">{senderDisplay()}</span>
    </div>
    <div class="field">
      <span class="label">Recipient</span>
      <span class="value">{recipientDisplay()}</span>
    </div>
    <div class="field">
      <span class="label">Date</span>
      <span class="value">{letter.created_at || ""}</span>
    </div>
    <div class="field">
      <span class="label">Object</span>
      <span class="value subject">{letter.object || "(untitled)"}</span>
    </div>
    <div class="field">
      <span class="label">UUID</span>
      <span class="value uuid">{letter.uuid || ""}</span>
    </div>
  </div>

  <hr />

  <div class="body-area">
    {#if body}
      <iframe class="letter-frame" srcdoc={body} sandbox="allow-same-origin" title="Letter body"></iframe>
    {:else}
      <p class="no-body">(No body content)</p>
    {/if}
  </div>

  {#if letter.thread && letter.thread.length > 1}
    <div class="thread-bar">
      <span class="thread-label">Thread ({letter.thread.length} letters)</span>
    </div>
  {/if}
</div>

<style>
  .letter-view {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-family: system-ui, monospace;
    font-size: 0.85rem;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 4px;
    padding: 6px 8px;
    border-bottom: 1px solid #333;
    background: #1a1a30;
    flex-shrink: 0;
    flex-wrap: wrap;
  }
  .tool-btn {
    display: flex;
    align-items: center;
    gap: 3px;
    padding: 3px 8px;
    background: transparent;
    border: 1px solid #444;
    border-radius: 4px;
    color: #b0b0c0;
    font-family: monospace;
    font-size: 0.75rem;
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
    white-space: nowrap;
  }
  .tool-btn:hover { background: #2a2a44; color: #e0e0e0; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .toolbar-spacer { flex: 1; }
  .meta-info { color: var(--clr-muted); font-size: 0.72rem; }

  .headers {
    padding: 8px 12px;
    flex-shrink: 0;
  }
  .field {
    display: flex;
    gap: 0.5rem;
    padding: 0.15rem 0;
  }
  .label {
    color: var(--clr-sub);
    min-width: 5rem;
    flex-shrink: 0;
  }
  .value {
    color: #e0e0e0;
    word-break: break-all;
  }
  .subject { font-weight: 600; }
  .uuid { color: var(--clr-muted); font-size: 0.78rem; }

  hr {
    border: none;
    border-top: 1px solid #333;
    margin: 0;
    flex-shrink: 0;
  }

  .body-area {
    flex: 1;
    overflow: hidden;
    display: flex;
    background: #fff;
  }
  .letter-frame {
    width: 100%;
    height: 100%;
    border: none;
    background: #fff;
    color: #000;
  }
  .no-body {
    color: var(--clr-muted);
    padding: 2rem;
    text-align: center;
    width: 100%;
    background: #1a1a2e;
  }

  .thread-bar {
    padding: 6px 12px;
    border-top: 1px solid #333;
    background: #16162a;
    flex-shrink: 0;
  }
  .thread-label {
    color: var(--clr-muted);
    font-size: 0.72rem;
  }

  /* Print styles — hide non-essential UI */
  @media print {
    :global(.tab-bar),
    :global(.command-bar),
    :global(.home-content),
    :global(.top-progress),
    .toolbar,
    .thread-bar {
      display: none !important;
    }
    .letter-view {
      padding: 0 !important;
      height: auto !important;
    }
    .headers {
      color: #000 !important;
    }
    .headers .value {
      color: #000 !important;
    }
    .headers .label {
      color: #444 !important;
    }
    .body-area {
      overflow: visible !important;
      background: #fff !important;
    }
    .letter-frame {
      color: #000 !important;
    }
    hr {
      border-top-color: #ccc !important;
    }
  }
</style>
