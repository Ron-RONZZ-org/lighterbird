<script>
  import { popup } from "./popupStore.svelte.js";
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi } from "./api.js";
  import { registerShortcuts } from "./keyboardShortcuts.svelte.js";
  import { openPrintWindow } from "./listTabShared.svelte.js";
  import { resolveCidUrls } from "./emailCidResolver.js";
  import { actionBanner } from "./actionBannerStore.svelte.js";
  import EmailHeaders from "./EmailHeaders.svelte";
  import EmailAttachmentBar from "./EmailAttachmentBar.svelte";
  import EmailConversationSidebar from "./EmailConversationSidebar.svelte";

  registerShortcuts("EmailViewTab", [
    { key: "Ctrl+R", desc: "Reply", modifiers: "Ctrl", category: "Email Detail" },
    { key: "Ctrl+Shift+R", desc: "Reply All", modifiers: "Ctrl+Shift", category: "Email Detail" },
    { key: "Ctrl+L", desc: "Forward", modifiers: "Ctrl", category: "Email Detail" },
    { key: "Ctrl+E", desc: "Export .eml", modifiers: "Ctrl", category: "Email Detail" },
    { key: "Ctrl+P", desc: "Print", modifiers: "Ctrl", category: "Email Detail" },
    { key: "Delete", desc: "Move to Trash", category: "Email Detail" },
    { key: "Ctrl+Delete", desc: "Permanently delete", modifiers: "Ctrl", category: "Email Detail" },
    { key: "Ctrl+S", desc: "Report spam", modifiers: "Ctrl", category: "Email Detail" },
    { key: "Ctrl+Shift+S", desc: "Report fraudulent", modifiers: "Ctrl+Shift", category: "Email Detail" },
    { key: "Ctrl+Right", desc: "Next unread", modifiers: "Ctrl", category: "Email Detail" },
    { key: "Ctrl+Left", desc: "Next unread", modifiers: "Ctrl", category: "Email Detail" },
  ]);

  let { data = {}, tabId } = $props();
  // svelte-ignore state_referenced_locally
  let msg = $state(data || {});
  let synced = $state(false);
  $effect(() => {
    if (!synced) {
      msg = data || {};
      synced = true;
    }
  });

  // Whether to prefer HTML rendering over plain text
  const LS_KEY = "lighterbird:email:viewHtml";
  function _loadHtmlPref() {
    try { const v = localStorage.getItem(LS_KEY); return v !== null ? JSON.parse(v) : true; }
    catch { return true; }
  }
  let useHtml = $state(_loadHtmlPref());
  $effect(() => {
    try { localStorage.setItem(LS_KEY, JSON.stringify(useHtml)); } catch { /* best-effort */ }
  });

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
    let h = resolveCidUrls(msg.html_body, msg.uuid);
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

  // ── Email actions ──────────────────────────────────────────────────────

  /** Quote the message body for reply/forward. */
  function quoteBody() {
    return (msg.body || "").split("\n").map(l => `> ${l}`).join("\n");
  }

  function parseRecipients(raw) {
    if (!raw) return [];
    if (Array.isArray(raw)) return raw.filter(Boolean);
    try { return JSON.parse(raw).filter(Boolean); } catch { return [raw].filter(Boolean); }
  }

  function reply() {
    const isFromSelf = msg.from_addr && msg.account_email &&
      msg.from_addr.toLowerCase().includes(msg.account_email.toLowerCase());
    const to = isFromSelf
      ? (parseRecipients(msg.to_recipients)[0] || "")
      : msg.from_addr || "";

    const subject = (msg.subject || "").toLowerCase().startsWith("re:")
      ? msg.subject : `Re: ${msg.subject}`;
    tabStore.open("form", "Reply", {
      form: "email-send",
      initialData: {
        _returnIdKey: "persistent-email-list",
        to,
        subject,
        body: `\n\n${quoteBody()}`,
        account: msg.account_email || "",
      },
    });
  }

  function replyAll() {
    const isFromSelf = msg.from_addr && msg.account_email &&
      msg.from_addr.toLowerCase().includes(msg.account_email.toLowerCase());

    let allTo, allCc;
    if (isFromSelf) {
      allTo = parseRecipients(msg.to_recipients).filter(Boolean).join(", ");
      allCc = parseRecipients(msg.cc_recipients).filter(Boolean).join(", ");
    } else {
      allTo = [
        msg.from_addr || "",
        ...parseRecipients(msg.to_recipients),
      ].filter(Boolean).join(", ");
      allCc = parseRecipients(msg.cc_recipients).filter(Boolean).join(", ");
    }

    const subject = (msg.subject || "").toLowerCase().startsWith("re:")
      ? msg.subject : `Re: ${msg.subject}`;
    tabStore.open("form", "Reply All", {
      form: "email-send",
      initialData: {
        _returnIdKey: "persistent-email-list",
        to: allTo,
        cc: allCc,
        subject,
        body: `\n\n${quoteBody()}`,
        account: msg.account_email || "",
      },
    });
  }

  function forward() {
    const subject = (msg.subject || "").toLowerCase().startsWith("fwd:")
      ? msg.subject : `Fwd: ${msg.subject}`;
    const header = `--- Forwarded message ---\nFrom: ${msg.from_addr || ""}\nSubject: ${msg.subject || ""}\nDate: ${msg.received_at || ""}\n\n`;
    tabStore.open("form", "Forward", {
      form: "email-send",
      initialData: {
        _returnIdKey: "persistent-email-list",
        subject,
        body: `\n\n${header}${msg.body || ""}`,
        account: msg.account_email || "",
      },
    });
  }

  function exportEml() {
    if (msg.uuid) {
      window.open(`/api/v1/email/export-eml/${msg.uuid}`, '_blank');
    }
  }

  function printEmail() {
    const headers = [
      { label: "From", value: msg.from_addr || "" },
      { label: "To", value: Array.isArray(msg.to_recipients) ? msg.to_recipients.join(", ") : (msg.to_recipients || "") },
      { label: "Date", value: msg.received_at || "" },
    ];
    const bodyContent = hasHtml && useHtml
      ? (msg.html_body || msg.body || "(no body)")
      : `<pre style="font-family:monospace;white-space:pre-wrap;">${msg.body || "(no body)"}</pre>`;
    openPrintWindow(msg.subject || "(no subject)", headers, bodyContent);
  }

  // ── Post-action helpers ────────────────────────────────────────────

  /** Dispatch event so list tabs can update. */
  function dispatchDeleted(action) {
    window.dispatchEvent(new CustomEvent("email-deleted", {
      detail: { uuid: msg.uuid, action },
    }));
  }

  /** Fetch the most recent unread email (different from current msg). */
  async function fetchNextUnread() {
    try {
      const result = await emailApi.listMessages({ read: false, sort: "newest", limit: 1 });
      const msgs = result.messages || [];
      if (msgs.length > 0 && msgs[0].uuid !== msg.uuid) {
        return msgs[0];
      }
    } catch { /* silent */ }
    return null;
  }

  /** Replace the current tab content with the next unread email. */
  async function showNextUnread() {
    const next = await fetchNextUnread();
    if (next) {
      msg = next;
      tabStore.update(tabId, next, next.subject || "(no subject)", `email-${next.uuid}`);
    }
  }

  /** Replace the current tab content with the next unread email
   *  (same as showNextUnread — both arrows do the same). */
  async function showPrevUnread() {
    await showNextUnread();
  }

  /**
   * Shared delete/post-action logic.
   * Fetches the next unread FIRST, then on success updates the current
   * tab in-place instead of closing+reopening.  The tab stays at the
   * same position in the tab bar with zero tab creation/destruction.
   *
   * @param {Function} apiCall - async function that performs the API call
   * @param {string} actionName - event detail action ("trash"|"hard_delete"|"spam"|"fraud")
   * @param {string} bannerMsg - message for the action banner
   */
  async function _performDeleteAction(apiCall, actionName, bannerMsg) {
    if (!msg.uuid) return;

    // Save original before we change anything (needed for undo)
    const originalMsg = { ...msg };

    // Fetch next unread BEFORE the API call (so we can update in-place)
    const nextMsg = await fetchNextUnread();

    try {
      const resp = await apiCall();
      const opId = resp?.operation_id;

      dispatchDeleted(actionName);

      if (nextMsg) {
        // Same tab, new content — update data, title, and idKey
        msg = nextMsg;
        tabStore.update(tabId, nextMsg, nextMsg.subject || "(no subject)", `email-${nextMsg.uuid}`);
      } else {
        // No more unread — close the tab
        tabStore.close(tabId);
      }

      const undoAction = opId
        ? async () => {
            try {
              await emailApi.undoAction(opId);
              // Re-fetch the restored message and open in a new tab
              try {
                const restored = await emailApi.getMessage(originalMsg.uuid);
                tabStore.open("email", restored.subject || "(no subject)", restored, {
                  idKey: `email-${restored.uuid}`,
                  replaceable: false,
                });
              } catch { /* silent */ }
            } catch { /* undo failed — ignore */ }
          }
        : null;

      actionBanner.show(bannerMsg, undoAction, "Undo");
    } catch { /* ignore */ }
  }

  /** Soft-delete with undo support. */
  async function trash() {
    await _performDeleteAction(
      () => emailApi.batchDelete([msg.uuid], 5),
      "trash",
      "Message moved to Trash",
    );
  }

  /** Hard-delete with undo support. */
  async function hardDelete() {
    await _performDeleteAction(
      () => emailApi.batchDeleteHard([msg.uuid], 5),
      "hard_delete",
      "Message permanently deleted",
    );
  }

  /** Report as spam with undo support. */
  async function reportSpam() {
    await _performDeleteAction(
      () => emailApi.reportSpam(msg.uuid, "spam", 5),
      "spam",
      "Message reported as spam",
    );
  }

  /** Report as fraudulent with undo support. */
  async function reportFraud() {
    await _performDeleteAction(
      () => emailApi.reportSpam(msg.uuid, "fraud", 5),
      "fraud",
      "Message reported as fraudulent",
    );
  }

  function handleKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "p") {
      e.preventDefault();
      printEmail();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "e") {
      e.preventDefault();
      exportEml();
      return;
    }
    // Delete key — soft delete (trash)
    if (!e.ctrlKey && !e.metaKey && !e.shiftKey && (e.key === "Delete" || e.key === "Del")) {
      e.preventDefault();
      trash();
      return;
    }
    // Ctrl+Delete — hard delete
    if ((e.ctrlKey || e.metaKey) && (e.key === "Delete" || e.key === "Del")) {
      e.preventDefault();
      hardDelete();
      return;
    }
    // Ctrl+S — report spam
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key === "s") {
      e.preventDefault();
      reportSpam();
      return;
    }
    // Ctrl+Shift+S — report fraudulent
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      reportFraud();
      return;
    }
    // Ctrl+Right — next unread
    if ((e.ctrlKey || e.metaKey) && (e.key === "ArrowRight")) {
      e.preventDefault();
      showNextUnread();
      return;
    }
    // Ctrl+Left — previous unread
    if ((e.ctrlKey || e.metaKey) && (e.key === "ArrowLeft")) {
      e.preventDefault();
      showPrevUnread();
      return;
    }
  }

  // Auto-mark as read when the email is opened
  let readAttempted = $state(false);
  $effect(() => {
    if (msg.uuid && !msg.is_read && !readAttempted) {
      readAttempted = true;
      markRead();
    }
  });

  async function markRead() {
    if (!msg.uuid || msg.is_read) return;
    try {
      await emailApi.markRead(msg.uuid, true);
      msg = { ...msg, is_read: true };
      tabStore.update(tabId, msg);
      window.dispatchEvent(new CustomEvent("email-read-status-changed", {
        detail: { uuid: msg.uuid, is_read: true },
      }));
    } catch { /* ignore */ }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="email-wrapper">
  <div class="email-view">
    <!-- Toolbar -->
    <div class="toolbar">
      <button class="tool-btn nav-arrow" onclick={showPrevUnread} title="Next unread (Ctrl+Left)">
        <span class="tool-icon">◀</span>
      </button>
      <button class="tool-btn" onclick={reply} title="Reply (Ctrl+R)">
        <span class="tool-icon">↩</span> Reply
      </button>
      <button class="tool-btn" onclick={replyAll} title="Reply All (Ctrl+Shift+R)">
        <span class="tool-icon">↩↩</span> Reply All
      </button>
      <button class="tool-btn" onclick={forward} title="Forward (Ctrl+L)">
        <span class="tool-icon">→</span> Forward
      </button>
      <button class="tool-btn" onclick={exportEml} title="Export .eml (Ctrl+E)">
        <span class="tool-icon">⬇</span> Export <kbd>E</kbd>
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
      <button class="tool-btn trash-btn" onclick={trash} title="Move to Trash (Delete)">
        <span class="tool-icon">🗑</span> <kbd>Del</kbd>
      </button>
      <button class="tool-btn danger-btn" onclick={hardDelete} title="Permanently delete (Ctrl+Delete)">
        <span class="tool-icon">✕</span> Hard Del <kbd>⌃Del</kbd>
      </button>
      <button class="tool-btn spam-btn" onclick={reportSpam} title="Report as spam (Ctrl+S)">
        <span class="tool-icon">⚠</span> Spam <kbd>⌃S</kbd>
      </button>
      <button class="tool-btn fraud-btn" onclick={reportFraud} title="Report as fraudulent (Ctrl+Shift+S)">
        <span class="tool-icon">⚡</span> Fraud <kbd>⌃⇧S</kbd>
      </button>
      <button class="tool-btn" onclick={printEmail} title="Print (Ctrl+P)">
        <span class="tool-icon">🖨</span> Print <kbd>Ctrl+P</kbd>
      </button>
      <div class="toolbar-spacer"></div>
      <button class="tool-btn nav-arrow" onclick={showNextUnread} title="Next unread (Ctrl+Right)">
        <span class="tool-icon">▶</span>
      </button>
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

    <!-- Headers (extracted) -->
    <EmailHeaders {msg} />

    <!-- Attachments (extracted, self-fetching) -->
    <EmailAttachmentBar msgUuid={msg.uuid || ""} attachmentCount={msg.attachment_count || 0} />

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

  <!-- Conversation sidebar (extracted) -->
  <EmailConversationSidebar
    show={showConversation}
    {conversation}
    loading={conversationLoading}
    currentUuid={msg.uuid || ""}
    onClose={() => { showConversation = false; }}
  />
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
  .tool-btn kbd {
    display: inline-block;
    padding: 0 3px;
    font-family: monospace;
    font-size: 0.65rem;
    background: #222;
    border: 1px solid #555;
    border-radius: 3px;
    color: #999;
    line-height: 1.3;
    margin-left: 1px;
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
  .nav-arrow {
    font-size: 0.8rem;
    padding: 3px 6px;
  }
  .toolbar-spacer {
    flex: 1;
  }
  .trash-btn:hover {
    border-color: #8b3a3a;
    color: #e06060;
  }
  .danger-btn {
    color: #c44;
  }
  .danger-btn:hover {
    border-color: #8b3a3a;
    background: #3a1a1a;
    color: #e06060;
  }
  .spam-btn {
    color: #d0a030;
  }
  .spam-btn:hover {
    border-color: #8b7a30;
    background: #3a2a0a;
    color: #e0c060;
  }
  .fraud-btn {
    color: #c07040;
  }
  .fraud-btn:hover {
    border-color: #8b5a3a;
    background: #3a2a1a;
    color: #e09060;
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
</style>
