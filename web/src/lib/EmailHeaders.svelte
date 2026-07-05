<script>
  let { msg = {} } = $props();

  let contactState = $state({ loading: false, done: false, error: "" });

  async function addContact() {
    if (!msg.uuid || contactState.loading || contactState.done) return;
    contactState.loading = true;
    contactState.error = "";
    try {
      const resp = await fetch(`/api/v1/email/messages/${msg.uuid}/add-contacts`, { method: "POST" });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || "Failed to add contact");
      }
      contactState.done = true;
    } catch (e) {
      contactState.error = e.message;
    } finally {
      contactState.loading = false;
    }
  }
</script>

<div class="headers">
  <div class="field">
    <span class="label">From</span>
    <span class="value from-row">
      <span class="from-addr">{msg.from_addr || ""}</span>
      {#if contactState.done}
        <span class="contact-badge added">✓ Contact</span>
      {:else if contactState.error}
        <span class="contact-badge error">{contactState.error}</span>
      {:else}
        <button class="contact-btn" onclick={addContact} disabled={contactState.loading}>
          {contactState.loading ? "..." : "+ Contact"}
        </button>
      {/if}
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
  .contact-btn:hover {
    background: #1a3a2a;
  }
  .contact-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .contact-badge {
    font-family: monospace;
    font-size: 0.68rem;
    padding: 1px 6px;
    border-radius: 3px;
    white-space: nowrap;
  }
  .contact-badge.added {
    background: #1a3a2a;
    color: #4a6;
    border: 1px solid #4a6;
  }
  .contact-badge.error {
    background: #3a1a1a;
    color: #e06060;
    border: 1px solid #8b3a3a;
  }
</style>
