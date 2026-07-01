<script>
  import { popup } from "./popupStore.svelte.js";
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi } from "./api.js";
  import { registerShortcuts } from "./keyboardShortcuts.svelte.js";

  registerShortcuts("EmailViewTab", [
    { key: "Ctrl+R", desc: "Reply", modifiers: "Ctrl", category: "Email Detail" },
    { key: "Ctrl+Shift+R", desc: "Reply All", modifiers: "Ctrl+Shift", category: "Email Detail" },
    { key: "Ctrl+L", desc: "Forward", modifiers: "Ctrl", category: "Email Detail" },
  ]);

  let { data = {}, tabId } = $props();
  let msg = $derived(data || {});

  // Whether to prefer HTML rendering over plain text
  let useHtml = $state(true);
  // Conversation sidebar state
  let showConversation = $state(false);
  let conversation = $state([]);
  let conversationLoading = $state(false);

  // Listen for keyboard shortcut custom events dispatched by App.svelte
  $effect(() => {
    function handler(e) {
      const action = e.detail?.action;
      if (action === 'reply') reply();
      else if (action === 'reply-all') replyAll();
      else if (action === 'forward') forward();
    }
    window.addEventListener('email-action', handler);
    return () => window.removeEventListener('email-action', handler);
  });

  /** Check if the email has an HTML body to render. */
  let hasHtml = $derived(!!(msg.html_body && msg.html_body.trim()));

  /** Normalize the HTML body for iframe rendering. */
  let htmlContent = $derived.by(() => {
    if (!hasHtml) return "";
    // Basic security: ensure it's a full document
    let h = msg.html_body;
    // If it's a fragment (no <html>/<body>), wrap it
    if (!/<\s*html\b/i.test(h)) {
      h = `<html><head><meta charset="utf-8"></head><body>${h}</body></html>`;
    }
    return h;
  });

  /** Toggle between HTML and plain text rendering. */
  function toggleRender() {
    if (hasHtml) {
      useHtml = !useHtml;
    }
  }

  /** Fetch conversation thread. */
  async function toggleConversation() {
    showConversation = !showConversation;
    if (showConversation && conversation.length === 0 && msg.uuid) {
      conversationLoading = true;
      try {
        const resp = await fetch(`/api/v1/email/messages/${msg.uuid}/conversation`);
        if (resp.ok) {
          const d = await resp.json();
          conversation = d.messages || [];
        }
      } catch { /* ignore */ }
      finally {
        conversationLoading = false;
      }
    }
  }

  /** Open a conversation message in a new tab. */
  function openConversationMsg(convMsg) {
    tabStore.open("email", convMsg.subject || "(no subject)", convMsg, {
      idKey: `email-${convMsg.uuid}`,
      replaceable: false,
    });
  }

  // ── Email actions ──────────────────────────────────────────────────────

  /** Quote the message body for reply/forward. */
  function quoteBody() {
    return (msg.body || "").split("\n").map(l => `> ${l}`).join("\n");
  }

  function reply() {
    const subject = (msg.subject || "").toLowerCase().startsWith("re:")
      ? msg.subject : `Re: ${msg.subject}`;
    tabStore.open("form", "Reply", {
      form: "email-send",
      initialData: {
        to: msg.from || "",
        subject,
        body: `\n\n${quoteBody()}`,
        account: msg.account_email || "",
      },
    });
  }

  function replyAll() {
    const subject = (msg.subject || "").toLowerCase().startsWith("re:")
      ? msg.subject : `Re: ${msg.subject}`;
    const allTo = [msg.from, ...(Array.isArray(msg.to) ? msg.to : [msg.to || ""])]
      .filter(Boolean).join(", ");
    tabStore.open("form", "Reply All", {
      form: "email-send",
      initialData: {
        to: allTo,
        subject,
        body: `\n\n${quoteBody()}`,
        account: msg.account_email || "",
      },
    });
  }

  function forward() {
    const subject = (msg.subject || "").toLowerCase().startsWith("fwd:")
      ? msg.subject : `Fwd: ${msg.subject}`;
    const header = `--- Forwarded message ---\nFrom: ${msg.from || ""}\nSubject: ${msg.subject || ""}\nDate: ${msg.received_at || ""}\n\n`;
    tabStore.open("form", "Forward", {
      form: "email-send",
      initialData: {
        subject,
        body: `\n\n${header}${msg.body || ""}`,
        account: msg.account_email || "",
      },
    });
  }

  async function markRead() {
    if (!msg.uuid || msg.is_read) return;
    try {
      await emailApi.markRead(msg.uuid, true);
      msg = { ...msg, is_read: true };
      tabStore.update(tabId, msg);
    } catch { /* ignore */ }
  }

  async function trash() {
    if (!msg.uuid) return;
    try {
      await fetch(`/api/v1/email/messages/${msg.uuid}/trash`, { method: "POST" });
      tabStore.close(tabId);
    } catch { /* ignore */ }
  }
</script>

<div class="email-wrapper">
  <div class="email-view">
    <!-- Toolbar -->
    <div class="toolbar">
      <button class="tool-btn" onclick={reply} title="Reply (Ctrl+R)">
        <span class="tool-icon">↩</span> Reply
      </button>
      <button class="tool-btn" onclick={replyAll} title="Reply All (Ctrl+Shift+R)">
        <span class="tool-icon">↩↩</span> Reply All
      </button>
      <button class="tool-btn" onclick={forward} title="Forward (Ctrl+L)">
        <span class="tool-icon">→</span> Forward
      </button>
      {#if hasHtml}
        <button class="tool-btn" onclick={toggleRender} title="Toggle HTML/plain text">
          <span class="tool-icon">{useHtml ? "🔤" : "🌐"}</span>
          {useHtml ? "Plain" : "HTML"}
        </button>
      {/if}
      <button class="tool-btn" onclick={markRead} disabled={msg.is_read} title="Mark as read">
        <span class="tool-icon">✓</span> Read
      </button>
      <button class="tool-btn trash-btn" onclick={trash} title="Trash">
        <span class="tool-icon">🗑</span>
      </button>
      <div class="toolbar-spacer"></div>
      <button
        class="tool-btn conv-btn"
        class:active={showConversation}
        onclick={toggleConversation}
        title="Conversation history"
      >
        <span class="tool-icon">💬</span>
        Thread
      </button>
    </div>

    <!-- Headers -->
    <div class="headers">
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
    </div>
    <hr />

    <!-- Body: HTML iframe or plain text -->
    <div class="body-area">
      {#if hasHtml && useHtml}
        <!-- svelte-ignore a11y_distracting_elements -->
        <iframe
          class="html-frame"
          srcdoc={htmlContent}
          sandbox="allow-same-origin"
          title="Email body"
        ></iframe>
      {:else}
        <pre class="plain-text">{msg.body || "(no body)"}</pre>
      {/if}
    </div>
  </div>

  <!-- Conversation sidebar (inside wrapper, does not cover tab bar) -->
  {#if showConversation}
    <!-- svelte-ignore a11y_click_events_have_key_events,a11y_no_static_element_interactions -->
    <div class="conv-overlay" role="presentation" onclick={() => { showConversation = false; }}>
      <!-- svelte-ignore a11y_click_events_have_key_events,a11y_no_static_element_interactions -->
      <div class="conv-panel" role="presentation" onclick={(e) => e.stopPropagation()}>
        <div class="conv-header">
          <span>Thread</span>
          <button class="close-btn" onclick={() => { showConversation = false; }}>✕</button>
        </div>
        <div class="conv-list">
          {#if conversationLoading}
            <p class="conv-loading">Loading…</p>
          {:else if conversation.length === 0}
            <p class="conv-empty">No other messages in this thread.</p>
          {:else}
            {#each conversation as cm}
              <div
                class="conv-item"
                class:active={cm.uuid === msg.uuid}
                role="button"
                tabindex="0"
                onclick={() => openConversationMsg(cm)}
                onkeydown={(e) => { if (e.key === 'Enter') openConversationMsg(cm); }}
              >
                <span class="conv-from">{(cm.from || "").slice(0, 24)}</span>
                <span class="conv-subject">{(cm.subject || "").slice(0, 32)}</span>
                <span class="conv-date">{cm.received_at || ""}</span>
              </div>
            {/each}
          {/if}
        </div>
      </div>
    </div>
  {/if}
</div>

<style>
  .email-wrapper {
    position: relative;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .email-view {
    font-family: system-ui, monospace;
    font-size: 0.85rem;
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }

  /* ── Toolbar ─────────────────────────────────────── */
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
  .tool-btn:hover {
    background: #2a2a44;
    color: #e0e0e0;
  }
  .tool-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .tool-btn.active {
    background: #2a2a44;
    color: #e0e0e0;
    border-color: #7c7c9a;
  }
  .tool-icon {
    font-size: 0.85rem;
  }
  .toolbar-spacer {
    flex: 1;
  }
  .trash-btn:hover {
    border-color: #8b3a3a;
    color: #e06060;
  }

  /* ── Headers ─────────────────────────────────────── */
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
  .subject {
    font-weight: 600;
  }
  hr {
    border: none;
    border-top: 1px solid #333;
    margin: 0;
    flex-shrink: 0;
  }

  /* ── Body area ───────────────────────────────────── */
  .body-area {
    flex: 1;
    overflow: hidden;
    display: flex;
  }
  .html-frame {
    width: 100%;
    height: 100%;
    border: none;
    background: #fff;
    color: #000;
  }
  .plain-text {
    flex: 1;
    margin: 0;
    padding: 12px;
    color: #ccc;
    white-space: pre-wrap;
    font-family: monospace;
    font-size: 0.82rem;
    line-height: 1.5;
    overflow-y: auto;
  }

  /* ── Conversation sidebar ────────────────────────── */
  .conv-overlay {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 100;
    display: flex;
    justify-content: flex-end;
  }
  .conv-panel {
    width: 340px;
    max-width: 90vw;
    background: #1e1e32;
    border-left: 1px solid #444;
    display: flex;
    flex-direction: column;
    animation: slideIn 0.15s ease;
  }
  @keyframes slideIn {
    from { transform: translateX(100%); }
    to { transform: translateX(0); }
  }
  .conv-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    border-bottom: 1px solid #333;
    font-family: monospace;
    font-size: 0.85rem;
    color: var(--clr-sub);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .close-btn {
    background: none;
    border: none;
    color: var(--clr-sub);
    font-size: 1rem;
    cursor: pointer;
    padding: 2px 4px;
  }
  .close-btn:hover { color: #fff; }
  .conv-list {
    flex: 1;
    overflow-y: auto;
    padding: 4px 0;
  }
  .conv-item {
    padding: 8px 12px;
    cursor: pointer;
    border-bottom: 1px solid #2a2a3e;
    transition: background 0.1s;
    font-family: monospace;
    font-size: 0.8rem;
  }
  .conv-item:hover { background: #2a2a44; }
  .conv-item.active {
    background: #252540;
    border-left: 3px solid #7c7c9a;
  }
  .conv-from { color: #e0e0e0; display: block; font-weight: 600; }
  .conv-subject { color: #b0b0c0; display: block; }
  .conv-date { color: var(--clr-muted); display: block; font-size: 0.7rem; margin-top: 2px; }
  .conv-loading, .conv-empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
    font-family: monospace;
    font-size: 0.8rem;
  }
</style>
