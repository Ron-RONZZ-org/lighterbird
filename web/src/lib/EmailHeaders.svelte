<script>
  import { email as emailApi } from "./api.js";
  import { tabStore } from "./tabStore.svelte.js";

  let { msg = {} } = $props();

  // ── Dialog state ──────────────────────────────────────────────────

  let showBlockDialog = $state(false);
  let showSpamDialog = $state(false);
  let actionError = $state("");

  /** Parse "Name <email>" or bare email into { name, email }. */
  function parseSender(raw) {
    const m = raw.match(/^(.*?)\s*<([^>]+)>$/);
    if (m) return { name: m[1].trim().replace(/^"|"$/g, ""), email: m[2].trim() };
    return { name: "", email: raw.trim() };
  }

  function openAddContact() {
    const raw = msg.from_addr || "";
    if (!raw || !raw.includes("@")) return;
    const { name, email } = parseSender(raw);
    const parts = name ? name.split(/\s+/) : [];
    const given = parts[0] || email.split("@")[0];
    const family = parts.slice(1).join(" ") || "";
    tabStore.open("form", "Add Contact", {
      form: "contacts-add",
      initialData: {
        _returnIdKey: "persistent-contacts-list",
        _returnType: "contacts-list",
        _returnTitle: "Contacts",
        "first-name": given,
        "last-name": family,
        email: email,
      },
    }, { idKey: "contacts-add" });
  }

  // ── Block actions ─────────────────────────────────────────────────

  function getSenderEmail() {
    const raw = msg.from_addr || "";
    const { email } = parseSender(raw);
    return email;
  }

  function getSenderDomain() {
    const email = getSenderEmail();
    if (!email || !email.includes("@")) return "";
    return email.split("@")[1];
  }

  async function blockSender() {
    actionError = "";
    const sender = getSenderEmail();
    if (!sender) return;
    try {
      // Dispatch CLI command via the existing REST API
      const resp = await fetch("/api/v1/command/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: `email block add ${sender}` }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        actionError = err.error || "Failed to block sender";
        return;
      }
      showBlockDialog = false;
    } catch (e) {
      actionError = `Error: ${e.message}`;
    }
  }

  async function blockDomain() {
    actionError = "";
    const domain = getSenderDomain();
    if (!domain) return;
    try {
      const resp = await fetch("/api/v1/command/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: `email block add @${domain}` }),
      });
      if (!resp.ok) {
        const err = await resp.json();
        actionError = err.error || "Failed to block domain";
        return;
      }
      showBlockDialog = false;
    } catch (e) {
      actionError = `Error: ${e.message}`;
    }
  }

  // ── Spam/Fraud actions ────────────────────────────────────────────

  async function reportSpam() {
    actionError = "";
    if (!msg.uuid) return;
    try {
      await emailApi.reportSpam(msg.uuid, "spam");
      showSpamDialog = false;
    } catch (e) {
      actionError = `Error: ${e.message}`;
    }
  }

  async function reportFraud() {
    actionError = "";
    if (!msg.uuid) return;
    try {
      await emailApi.reportSpam(msg.uuid, "fraud");
      showSpamDialog = false;
    } catch (e) {
      actionError = `Error: ${e.message}`;
    }
  }

  // ── Keyboard trap for dialogs ─────────────────────────────────────

  function trapKeydown(e, closeFn) {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      closeFn();
    }
  }
</script>

<div class="headers">
  <div class="field">
    <span class="label">From</span>
    <span class="value from-row">
      <span class="from-addr">{msg.from_addr || ""}</span>
      <button class="contact-btn" onclick={openAddContact}>+ Contact</button>
      <button class="block-btn" onclick={() => (showBlockDialog = true)} title="Block sender or domain">🗑 Block</button>
      <button class="spam-btn" onclick={() => (showSpamDialog = true)} title="Report spam or fraudulent">⚠ Spam</button>
    </span>
  </div>
  <div class="field">
    <span class="label">To</span>
    <span class="value">
      {Array.isArray(msg.to_recipients) ? msg.to_recipients.join(", ") : (msg.to_recipients || "")}
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

<!-- Block Dialog -->
{#if showBlockDialog}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="confirm-overlay" role="alertdialog" aria-modal="true" aria-label="Block sender"
       onclick={() => (showBlockDialog = false)}
       onkeydown={(e) => trapKeydown(e, () => (showBlockDialog = false))} tabindex="0">
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="confirm-box" onclick={(e) => e.stopPropagation()}>
      <h3 class="confirm-title" style="color: #e06060;">Block</h3>
      <p>How would you like to block this sender?</p>
      {#if actionError}
        <p class="error-msg">{actionError}</p>
      {/if}
      <div class="multi-actions">
        <button class="btn danger" onclick={blockSender}>Block Sender</button>
        <button class="btn danger" onclick={blockDomain}>Block Domain</button>
        <button class="btn" onclick={() => { showBlockDialog = false; actionError = ""; }}>Cancel</button>
      </div>
    </div>
  </div>
{/if}

<!-- Spam Dialog -->
{#if showSpamDialog}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="confirm-overlay" role="alertdialog" aria-modal="true" aria-label="Report spam"
       onclick={() => (showSpamDialog = false)}
       onkeydown={(e) => trapKeydown(e, () => (showSpamDialog = false))} tabindex="0">
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="confirm-box" onclick={(e) => e.stopPropagation()}>
      <h3 class="confirm-title" style="color: #d0a030;">Report</h3>
      <p>Mark this message as:</p>
      {#if actionError}
        <p class="error-msg">{actionError}</p>
      {/if}
      <div class="multi-actions">
        <button class="btn warning" onclick={reportSpam}>Spam</button>
        <button class="btn danger" onclick={reportFraud}>Fraudulent</button>
        <button class="btn" onclick={() => { showSpamDialog = false; actionError = ""; }}>Cancel</button>
      </div>
    </div>
  </div>
{/if}

<style>
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
  .from-row {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .from-addr {
    word-break: break-all;
  }
  .contact-btn {
    font-family: monospace;
    font-size: 0.68rem;
    padding: 1px 6px;
    background: transparent;
    border: 1px solid #4a6;
    border-radius: 3px;
    color: #4a6;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.1s;
  }
  .contact-btn:hover { background: #1a3a2a; }
  .contact-btn:disabled { opacity: 0.5; cursor: default; }

  .block-btn {
    font-family: monospace;
    font-size: 0.68rem;
    padding: 1px 6px;
    background: transparent;
    border: 1px solid #c44;
    border-radius: 3px;
    color: #c44;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.1s;
  }
  .block-btn:hover { background: #3a1a1a; }

  .spam-btn {
    font-family: monospace;
    font-size: 0.68rem;
    padding: 1px 6px;
    background: transparent;
    border: 1px solid #c90;
    border-radius: 3px;
    color: #c90;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.1s;
  }
  .spam-btn:hover { background: #3a2a0a; }

  .confirm-overlay {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }
  .confirm-box {
    background: #22223a;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 1.5rem 2rem;
    text-align: center;
    font-family: system-ui, monospace;
    max-width: 420px;
  }
  .confirm-title {
    font-size: 1rem;
    margin-bottom: 0.6rem;
    font-weight: 600;
  }
  .confirm-box p {
    margin-bottom: 1rem;
    color: #e0e0e0;
    font-size: 0.89rem;
    line-height: 1.5;
  }
  .error-msg {
    color: #e06060;
    font-size: 0.82rem;
    margin-bottom: 0.6rem;
  }
  .multi-actions {
    display: flex;
    gap: 0.75rem;
    justify-content: center;
    flex-wrap: wrap;
  }
  .btn {
    padding: 0.4rem 1rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #2a2a3e;
    color: #e0e0e0;
    cursor: pointer;
    font-size: 0.85rem;
    font-family: monospace;
    transition: background 0.1s;
  }
  .btn:hover { background: #3a3a5e; }
  .btn.danger { background: #6b2020; border-color: #8b3030; }
  .btn.danger:hover { background: #8b3030; }
  .btn.warning { background: #6b5a20; border-color: #8b7a30; }
  .btn.warning:hover { background: #8b7a30; }
</style>
