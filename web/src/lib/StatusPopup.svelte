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
        <span class="val">{(msg.from || "").slice(0, 28)}</span>
        <span class="hint">{(msg.subject || "").slice(0, 28)}</span>
      </div>
    {:else}
      <p class="empty">No messages.</p>
    {/each}
  {:else if d.todos}
    {#each d.todos as todo}
      <div class="row">
        <span class="key">{todo.uuid?.slice(0, 8) || ""}</span>
        <span class="val">{(todo.title || "").slice(0, 36)}</span>
        <span class="hint">{todo.status || ""}</span>
      </div>
    {:else}
      <p class="empty">No todos.</p>
    {/each}
  {:else if d.contacts}
    {#each d.contacts as contact}
      <div class="row">
        <span class="key">{contact.uuid?.slice(0, 8) || ""}</span>
        <span class="val">{(contact.name || "").slice(0, 24)}</span>
        <span class="hint">{contact.email || ""}</span>
      </div>
    {:else}
      <p class="empty">No contacts.</p>
    {/each}
  {:else if d.entries}
    {#each d.entries as entry}
      <div class="row">
        <span class="key">{entry.uuid?.slice(0, 8) || ""}</span>
        <span class="val">{(entry.title || "").slice(0, 32)}</span>
        <span class="hint">{entry.date || ""}</span>
      </div>
    {:else}
      <p class="empty">No journal entries.</p>
    {/each}
  {:else if d.uuid}
    <div class="row">
      <span class="key">{d.uuid?.slice(0, 8) || ""}</span>
      <span class="val">{d.title || d.email || ""}</span>
    </div>
  {:else if d.title}
    <p class="message">{d.title}</p>
  {:else if d.message}
    <p class="message">{d.message}</p>
  {:else if d.status}
    <p class="message">{d.status}</p>
  {:else if d.removed}
    <p class="message">Removed: {d.removed.join(", ")}</p>
  {:else if d.done}
    <p class="message">Done: {d.done.join(", ")}</p>
  {:else if d._summary}
    <p class="message" style="white-space:pre-wrap">{d._summary}</p>
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
