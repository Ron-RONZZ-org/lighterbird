<script>
  let { data = {} } = $props();
  // Normalize null to empty object (delete commands return 204 → null)
  let d = $derived(data || {});
</script>

<div class="status">
  {#if d.accounts}
    {#each d.accounts as account}
      <div class="row">
        <span class="key">{account.uuid?.slice(0, 8) || ""}</span>
        <span class="val">{account.email || ""}</span>
        <span class="hint">{account.name || ""}</span>
      </div>
    {:else}
      <p class="empty">No accounts configured.</p>
    {/each}
  {:else if d.calendars}
    {#each d.calendars as cal}
      <div class="row">
        <span class="key">{cal.uuid?.slice(0, 8) || ""}</span>
        <span class="val">{cal.url || ""}</span>
        <span class="hint">{cal.remote ? "remote" : "local"}</span>
      </div>
    {:else}
      <p class="empty">No calendars configured.</p>
    {/each}
  {:else if d.messages}
    {#each d.messages as msg}
      <div class="row">
        <span class="key">{msg.uuid?.slice(0, 8) || ""}</span>
        <span class="val">{(msg.de || "").slice(0, 28)}</span>
        <span class="hint">{(msg.subjekto || "").slice(0, 28)}</span>
      </div>
    {:else}
      <p class="empty">No messages.</p>
    {/each}
  {:else if d.message}
    <p class="message">{d.message}</p>
  {:else if d.status}
    <p class="message">{d.status}</p>
  {:else}
    <p class="message">Done.</p>
  {/if}
</div>

<style>
  .status {
    font-family: monospace;
    font-size: 0.85rem;
  }
  .row {
    display: flex;
    gap: 0.5rem;
    padding: 0.3rem 0;
    border-bottom: 1px solid #2a2a3e;
  }
  .row:last-child {
    border-bottom: none;
  }
  .key {
    color: #7c7c9a;
    min-width: 5rem;
  }
  .val {
    color: #e0e0e0;
    min-width: 12rem;
  }
  .hint {
    color: #5a5a7a;
  }
  .empty {
    color: #5a5a7a;
    text-align: center;
    padding: 2rem;
  }
  .message {
    color: #e0e0e0;
    white-space: pre-wrap;
  }
</style>
