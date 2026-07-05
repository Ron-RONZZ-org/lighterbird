<script>
  import { tabStore } from "./tabStore.svelte.js";

  let { msg = {} } = $props();

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
</script>

<div class="headers">
  <div class="field">
    <span class="label">From</span>
    <span class="value from-row">
      <span class="from-addr">{msg.from_addr || ""}</span>
      <button class="contact-btn" onclick={openAddContact}>+ Contact</button>
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
</style>
