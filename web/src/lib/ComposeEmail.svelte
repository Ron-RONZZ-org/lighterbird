<script>
  /** Email compose form — used when !email send is typed interactively. */

  import { email as emailApi } from "./api.js";

  let { initialData = {}, onsubmit } = $props();
  // svelte-ignore state_referenced_locally
  const _initial = initialData;

  let accountUuid = $state(_initial.account || "");
  let to = $state(_initial.to || "");
  let subject = $state(_initial.subject || "");
  let body = $state(_initial.body || "");
  let cc = $state(_initial.cc || "");
  let sending = $state(false);
  let accounts = $state([]);

  $effect(() => {
    emailApi.listAccounts().then((data) => {
      accounts = data.accounts || [];
      if (accounts.length > 0 && !accountUuid) {
        accountUuid = accounts[0].uuid;
      }
    }).catch(() => {});
  });

  async function handleSubmit(e) {
    e.preventDefault();
    if (!to || !subject) return;
    sending = true;
    try {
      await onsubmit({
        tokens: ["email", "send"],
        flags: {
          ...(accountUuid ? { account: accountUuid } : {}),
          ...(cc ? { cc } : {}),
        },
        remaining: [to, subject, body],
      });
    } finally {
      sending = false;
    }
  }
</script>

<form onsubmit={handleSubmit} class="email-form">
  <div class="field">
    <label for="account">Account</label>
    <select id="account" bind:value={accountUuid}>
      {#each accounts as acct}
        <option value={acct.uuid}>{acct.email}</option>
      {/each}
    </select>
  </div>
  <div class="field">
    <label for="to">To</label>
    <input id="to" type="email" bind:value={to} required placeholder="recipient@example.com" />
  </div>
  <div class="field">
    <label for="cc">CC</label>
    <input id="cc" type="email" bind:value={cc} placeholder="cc@example.com (optional)" />
  </div>
  <div class="field">
    <label for="subject">Subject</label>
    <input id="subject" type="text" bind:value={subject} required placeholder="Subject" />
  </div>
  <div class="field">
    <label for="body">Body</label>
    <textarea id="body" bind:value={body} rows="8" placeholder="Message body..."></textarea>
  </div>
  <div class="actions">
    <button type="submit" disabled={sending || !to || !subject}>
      {sending ? "Sending..." : "Send"}
    </button>
  </div>
</form>

<style>
  .email-form { padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label { font-size: 0.8rem; color: #7c7c9a; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .field input, .field select, .field textarea {
    background: #16213e; border: 1px solid #333; color: #e0e0e0;
    padding: 0.5rem; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
  }
  .field textarea { resize: vertical; min-height: 100px; }
  .actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
  .actions button {
    background: #0f3460; color: #e0e0e0; border: none; padding: 0.5rem 1.5rem;
    border-radius: 4px; cursor: pointer; font-size: 0.9rem;
  }
  .actions button:disabled { opacity: 0.5; cursor: not-allowed; }
  .actions button:hover:not(:disabled) { background: #1a4a7a; }
</style>
