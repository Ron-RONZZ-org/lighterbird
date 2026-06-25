<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { calendar as calendarApi, llm as llmApi } from "./api.js";
  import AccountList from "./AccountList.svelte";
  import LlmProfileForm from "./LlmProfileForm.svelte";
  import EmailAccountForm from "./EmailAccountForm.svelte";
  import CalendarAccountForm from "./CalendarAccountForm.svelte";

  let { data = {} } = $props();
  // Normalize null to empty object (delete commands return 204 → null)
  let d = $derived(data || {});

  // Dismissible notice banner — local state only (resets on page reload)
  let noticeDismissed = $state(false);

  function dismissNotice() {
    noticeDismissed = true;
  }

  // ── Form overlay state ──────────────────────────────────────────────

  let activeForm = $state(null); // null | "llm" | "email" | "calendar"
  let editingItem = $state(null);

  function openForm(type, item = null) {
    activeForm = type;
    editingItem = item;
  }

  function closeForm() {
    activeForm = null;
    editingItem = null;
  }

  /** Re-execute the current command to refresh the list after save/delete. */
  async function refreshList() {
    // Re-trigger the command that generated this data
    // We use the tab store to know which tab is active and re-execute
    const active = tabStore.active;
    if (!active) return;
    try {
      const resp = await fetch("/api/v1/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tokens: [], flags: {} }),
      });
      // This is a soft approach — we just update the tab data directly
      // by re-running the command via the command dispatch.
    } catch {}
  }

  /** Activate an LLM profile. */
  async function activateProfile(item) {
    try {
      await llmApi.loadProfile(item.name);
      // Show brief success by updating the tab with refreshed data
      await refetchCurrentTab();
    } catch (err) {
      alert(`Failed to activate: ${err.message}`);
    }
  }

  /** Remove an item with confirmation. */
  async function removeItem(type, item) {
    if (!confirm(`Remove this ${type} account/profile?`)) return;
    try {
      if (type === "email") {
        await emailApi.deleteAccount(item.uuid);
      } else if (type === "calendar") {
        await calendarApi.deleteCalendar(item.uuid);
      } else if (type === "llm") {
        await llmApi.deleteProfile(item.name);
      }
      closeForm();
      // Re-fetch data by issuing the same command
      await refetchCurrentTab();
    } catch (err) {
      alert(`Failed to remove: ${err.message}`);
    }
  }

  /** Re-fetch the data for the current tab by re-executing the command. */
  async function refetchCurrentTab() {
    const active = tabStore.active;
    if (!active) return;
    try {
      let result;
      if (d.accounts !== undefined) {
        result = await emailApi.listAccounts();
      } else if (d.calendars !== undefined) {
        result = await calendarApi.listCalendars();
      } else if (d.profiles !== undefined) {
        result = await llmApi.listProfiles();
      }
      if (result) {
        tabStore.update(active.id, result);
      }
    } catch {}
  }

</script>

<div class="status">
  {#if d._notice && !noticeDismissed}
    <div class="notice-banner" role="alert">
      <span class="notice-text">{d._notice.message}</span>
      <button class="notice-close" onclick={dismissNotice} aria-label="Dismiss notice">✕</button>
    </div>
  {/if}
  {#if d.accounts !== undefined}
    {#if activeForm === "email"}
      <EmailAccountForm
        account={editingItem}
        onSaved={() => { closeForm(); refetchCurrentTab(); }}
        onDismiss={closeForm}
      />
    {/if}
    <AccountList
      type="email"
      items={d.accounts}
      onAdd={() => openForm("email")}
      onModify={(item) => openForm("email", item)}
      onRemove={(item) => removeItem("email", item)}
    />

  {:else if d.calendars !== undefined}
    {#if activeForm === "calendar"}
      <CalendarAccountForm
        calendar={editingItem}
        onSaved={() => { closeForm(); refetchCurrentTab(); }}
        onDismiss={closeForm}
      />
    {/if}
    <AccountList
      type="calendar"
      items={d.calendars}
      onAdd={() => openForm("calendar")}
      onModify={(item) => openForm("calendar", item)}
      onRemove={(item) => removeItem("calendar", item)}
    />

  {:else if d.profiles !== undefined}
    {#if activeForm === "llm"}
      <LlmProfileForm
        profile={editingItem}
        onSaved={() => { closeForm(); refetchCurrentTab(); }}
        onDismiss={closeForm}
      />
    {/if}
    <AccountList
      type="llm"
      items={d.profiles}
      activeName={d.active_profile || ""}
      onAdd={() => openForm("llm")}
      onModify={(item) => openForm("llm", item)}
      onRemove={(item) => removeItem("llm", item)}
      onActivate={(item) => activateProfile(item)}
    />

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
    color: var(--clr-sub);
    min-width: 5rem;
  }
  .val {
    color: #e0e0e0;
    min-width: 12rem;
  }
  .hint {
    color: var(--clr-muted);
  }
  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }
  .message {
    color: #e0e0e0;
    white-space: pre-wrap;
  }
  .notice-banner {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 8px 10px;
    margin: 4px 8px;
    background: #2a2a3e;
    border: 1px solid #4a4a6e;
    border-radius: 6px;
    font-size: 0.78rem;
    color: #c0c0d0;
    line-height: 1.4;
  }
  .notice-text {
    flex: 1;
    white-space: pre-wrap;
  }
  .notice-close {
    flex-shrink: 0;
    background: none;
    border: none;
    color: #888;
    font-size: 0.85rem;
    cursor: pointer;
    padding: 2px 4px;
    border-radius: 3px;
    line-height: 1;
  }
  .notice-close:hover {
    color: #e0e0e0;
    background: #3a3a4e;
  }
</style>
