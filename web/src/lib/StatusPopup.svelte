<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { calendar as calendarApi, llm as llmApi, email as emailApi, contacts as contactsApi, todo as todoApi, journal as journalApi } from "./api.js";
  import AccountList from "./AccountList.svelte";
  import LlmProfileForm from "./LlmProfileForm.svelte";
  import EmailAccountForm from "./EmailAccountForm.svelte";
  import CalendarAccountForm from "./CalendarAccountForm.svelte";
  import BackupStrategyList from "./BackupStrategyList.svelte";
  import BackupStrategyForm from "./BackupStrategyForm.svelte";

  let { data = {} } = $props();
  // Normalize null to empty object (delete commands return 204 → null)
  let d = $derived(data || {});

  // ── Form overlay state ──────────────────────────────────────────────

  let activeForm = $state(null); // null | "llm" | "email" | "calendar" | "backup-strategy" | "contacts" | "todo" | "journal-write"
  let editingItem = $state(null); // existing item for edit, or initialData for new

  // Auto-show form when the tab data includes autoAdd flag
  $effect(() => {
    if (d.autoAdd && d.addFormType && !activeForm) {
      activeForm = d.addFormType;
      if (d.addInitialData && Object.keys(d.addInitialData).length > 0) {
        editingItem = d.addInitialData;
      }
    }
  });

  // Backup strategy testing state
  let testingStrategies = $state(new Set());
  let testResults = $state({});

  function openForm(type, item = null) {
    activeForm = type;
    editingItem = item;
  }

  function closeForm() {
    activeForm = null;
    editingItem = null;
  }

  /** Activate an LLM profile. */
  async function activateProfile(item) {
    try {
      await llmApi.loadProfile(item.name);
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
      } else if (type === "backup-strategy") {
        await fetch("/api/v1/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tokens: ["backup", "config", "remove", item.id], flags: {} }),
        });
      } else if (type === "contacts") {
        await contactsApi.delete(item.uuid);
      } else if (type === "todo") {
        await todoApi.delete(item.uuid);
      } else if (type === "journal") {
        await journalApi.delete(item.uuid);
      }
      closeForm();
      await refetchCurrentTab();
    } catch (err) {
      alert(`Failed to remove: ${err.message}`);
    }
  }

  /** Test a backup strategy's target. */
  async function testStrategy(item) {
    const sid = item.id;
    testingStrategies = new Set([...testingStrategies, sid]);
    testResults = { ...testResults, [sid]: null };
    try {
      const resp = await fetch("/api/v1/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tokens: ["backup", "config", "test", sid], flags: {} }),
      });
      const result = await resp.json();
      if (resp.ok) {
        testResults = { ...testResults, [sid]: { success: true, message: result.data?.message || "Target is writable." } };
      } else {
        const detail = result.detail || {};
        const msg = typeof detail === "string" ? detail : detail.error || "Test failed";
        testResults = { ...testResults, [sid]: { success: false, message: msg } };
      }
    } catch (err) {
      testResults = { ...testResults, [sid]: { success: false, message: err.message || "Network error" } };
    } finally {
      const next = new Set(testingStrategies);
      next.delete(sid);
      testingStrategies = next;
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
      } else if (d.strategies !== undefined) {
        const resp = await fetch("/api/v1/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tokens: ["backup", "config", "list"], flags: {} }),
        });
        const cmdResult = await resp.json();
        if (resp.ok) {
          result = cmdResult.data;
          if (cmdResult.title) {
            tabStore.update(active.id, result, cmdResult.title);
            return;
          }
        }
      } else if (d.contacts !== undefined) {
        result = await contactsApi.list({ limit: 50 });
      } else if (d.todos !== undefined) {
        result = await todoApi.list({ limit: 50 });
      } else if (d.entries !== undefined) {
        result = await journalApi.list({ limit: 50 });
      }
      if (result) {
        tabStore.update(active.id, result);
      }
    } catch { /* ignore */ }
  }

  /** Save a contacts item via the contacts API. */
  async function saveContact(data) {
    await contactsApi.create(data);
    closeForm();
    await refetchCurrentTab();
  }

  /** Save a todo item via the todo API. */
  async function saveTodo(data) {
    await todoApi.create(data);
    closeForm();
    await refetchCurrentTab();
  }

  /** Save a journal entry via the journal API. */
  async function saveJournal(data) {
    await journalApi.create(data);
    closeForm();
    await refetchCurrentTab();
  }

  // ── Inline form state for contacts ─────────────────────────────────
  let contactName = $state("");
  let contactEmail = $state("");
  let contactPhone = $state("");
  let contactOrg = $state("");
  let savingContact = $state(false);
  let contactError = $state("");

  function resetContactForm(initialData) {
    contactName = initialData?.name || "";
    contactEmail = initialData?.email || "";
    contactPhone = initialData?.phone || "";
    contactOrg = initialData?.org || "";
    contactError = "";
  }

  async function handleSaveContact() {
    if (!contactName.trim()) {
      contactError = "Name is required.";
      return;
    }
    savingContact = true;
    contactError = "";
    try {
      const data = { name: contactName.trim() };
      if (contactEmail.trim()) data.email = contactEmail.trim();
      if (contactPhone.trim()) data.phone = contactPhone.trim();
      if (contactOrg.trim()) data.org = contactOrg.trim();
      await contactsApi.create(data);
      closeForm();
      await refetchCurrentTab();
    } catch (err) {
      contactError = err.message || "Failed to save contact.";
    } finally {
      savingContact = false;
    }
  }

  // ── Inline form state for todos ────────────────────────────────────
  let todoTitle = $state("");
  let todoDescription = $state("");
  let todoPriority = $state("5");
  let todoDue = $state("");
  let savingTodo = $state(false);
  let todoError = $state("");

  function resetTodoForm(initialData) {
    todoTitle = initialData?.title || "";
    todoDescription = initialData?.description || "";
    todoPriority = initialData?.priority || "5";
    todoDue = initialData?.due || "";
    todoError = "";
  }

  async function handleSaveTodo() {
    if (!todoTitle.trim()) {
      todoError = "Title is required.";
      return;
    }
    savingTodo = true;
    todoError = "";
    try {
      const data = { title: todoTitle.trim() };
      if (todoDescription.trim()) data.description = todoDescription.trim();
      if (todoPriority) data.priority = parseInt(todoPriority, 10);
      if (todoDue) data.due = todoDue;
      await todoApi.create(data);
      closeForm();
      await refetchCurrentTab();
    } catch (err) {
      todoError = err.message || "Failed to save todo.";
    } finally {
      savingTodo = false;
    }
  }

  // ── Inline form state for journal ──────────────────────────────────
  let journalTitle = $state("");
  let journalText = $state("");
  let journalDate = $state(new Date().toISOString().slice(0, 10));
  let savingJournal = $state(false);
  let journalError = $state("");

  function resetJournalForm(initialData) {
    journalTitle = initialData?.title || "";
    journalText = initialData?.text || initialData?.body || "";
    journalDate = initialData?.date || new Date().toISOString().slice(0, 10);
    journalError = "";
  }

  async function handleSaveJournal() {
    if (!journalTitle.trim()) {
      journalError = "Title is required.";
      return;
    }
    savingJournal = true;
    journalError = "";
    try {
      const data = { title: journalTitle.trim(), text: journalText };
      if (journalDate) data.date = journalDate;
      await journalApi.create(data);
      closeForm();
      await refetchCurrentTab();
    } catch (err) {
      journalError = err.message || "Failed to save journal entry.";
    } finally {
      savingJournal = false;
    }
  }

  // Reset inline form when activeForm changes to a new type
  $effect(() => {
    if (activeForm === "contacts") {
      const initData = editingItem && !editingItem.uuid ? editingItem : {};
      resetContactForm(initData);
    } else if (activeForm === "todo") {
      const initData = editingItem && !editingItem.uuid ? editingItem : {};
      resetTodoForm(initData);
    } else if (activeForm === "journal-write") {
      const initData = editingItem && !editingItem.uuid ? editingItem : {};
      resetJournalForm(initData);
    }
  });
</script>

<div class="status">
  {#if d.accounts !== undefined}
    {#if activeForm === "email"}
      <EmailAccountForm
        account={editingItem?.uuid ? editingItem : null}
        initialData={!editingItem?.uuid ? editingItem : null}
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
        calendar={editingItem?.uuid ? editingItem : null}
        initialData={!editingItem?.uuid ? editingItem : null}
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

  {:else if d.strategies !== undefined}
    {#if activeForm === "backup-strategy"}
      <BackupStrategyForm
        strategy={editingItem}
        onSaved={() => { closeForm(); refetchCurrentTab(); }}
        onDismiss={closeForm}
      />
    {/if}
    <BackupStrategyList
      items={d.strategies}
      {testingStrategies}
      {testResults}
      onAdd={() => openForm("backup-strategy")}
      onModify={(item) => openForm("backup-strategy", item)}
      onRemove={(item) => removeItem("backup-strategy", item)}
      onTest={(item) => testStrategy(item)}
    />

  {:else if d.contacts !== undefined}
    {#if activeForm === "contacts"}
      <div class="modal-overlay" onclick={closeForm} onkeydown={(e) => e.key === "Escape" && closeForm()} role="button" tabindex="-1" aria-label="Dismiss">
        <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
          <div class="modal-header">
            <h2>Add Contact</h2>
          </div>
          <div class="form">
            <label class="field">
              <span class="field-label">Name *</span>
              <input type="text" class="text-input" bind:value={contactName} placeholder="Full name" autofocus />
            </label>
            <label class="field">
              <span class="field-label">Email</span>
              <input type="email" class="text-input" bind:value={contactEmail} placeholder="email@example.com" />
            </label>
            <label class="field">
              <span class="field-label">Phone</span>
              <input type="text" class="text-input" bind:value={contactPhone} placeholder="+1-555-1234" />
            </label>
            <label class="field">
              <span class="field-label">Organization</span>
              <input type="text" class="text-input" bind:value={contactOrg} placeholder="Company name" />
            </label>
            {#if contactError}
              <p class="error">{contactError}</p>
            {/if}
            <div class="form-actions">
              <button class="btn-primary" onclick={handleSaveContact} disabled={savingContact || !contactName.trim()}>
                {savingContact ? "Saving…" : "Add Contact"}
              </button>
              <button class="btn-secondary" onclick={closeForm}>Cancel</button>
            </div>
          </div>
        </div>
      </div>
    {/if}
    <div class="section-header">
      <h3 class="title">Contacts</h3>
      <button class="btn-add" onclick={() => { resetContactForm({}); openForm("contacts"); }}>+ Add Contact</button>
    </div>
    {#if d.contacts.length === 0}
      <p class="empty">No contacts.</p>
    {:else}
      {#each d.contacts as contact}
        <div class="row">
          <span class="key">{contact.uuid?.slice(0, 8) || ""}</span>
          <span class="val">{(contact.nomo || contact.name || "").slice(0, 24)}</span>
          <span class="hint">{contact.retposto || contact.email || ""}</span>
          <div class="row-actions">
            <button class="btn-remove-sm" onclick={() => removeItem("contacts", contact)} title="Remove">✕</button>
          </div>
        </div>
      {/each}
    {/if}

  {:else if d.todos !== undefined}
    {#if activeForm === "todo"}
      <div class="modal-overlay" onclick={closeForm} onkeydown={(e) => e.key === "Escape" && closeForm()} role="button" tabindex="-1" aria-label="Dismiss">
        <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
          <div class="modal-header">
            <h2>Add Todo</h2>
          </div>
          <div class="form">
            <label class="field">
              <span class="field-label">Title *</span>
              <input type="text" class="text-input" bind:value={todoTitle} placeholder="What needs to be done?" autofocus />
            </label>
            <label class="field">
              <span class="field-label">Description</span>
              <textarea class="text-input textarea" bind:value={todoDescription} rows="3" placeholder="Optional details..."></textarea>
            </label>
            <div class="row-fields">
              <label class="field">
                <span class="field-label">Priority (1-10)</span>
                <input type="number" class="text-input" bind:value={todoPriority} min="1" max="10" />
              </label>
              <label class="field">
                <span class="field-label">Due Date</span>
                <input type="date" class="text-input" bind:value={todoDue} />
              </label>
            </div>
            {#if todoError}
              <p class="error">{todoError}</p>
            {/if}
            <div class="form-actions">
              <button class="btn-primary" onclick={handleSaveTodo} disabled={savingTodo || !todoTitle.trim()}>
                {savingTodo ? "Saving…" : "Add Todo"}
              </button>
              <button class="btn-secondary" onclick={closeForm}>Cancel</button>
            </div>
          </div>
        </div>
      </div>
    {/if}
    <div class="section-header">
      <h3 class="title">Todos</h3>
      <button class="btn-add" onclick={() => { resetTodoForm({}); openForm("todo"); }}>+ Add Todo</button>
    </div>
    {#each d.todos as todo}
      <div class="row">
        <span class="key">{todo.uuid?.slice(0, 8) || ""}</span>
        <span class="val">{(todo.titolo || todo.title || "").slice(0, 36)}</span>
        <span class="hint">{todo.status || ""}</span>
        <div class="row-actions">
          <button class="btn-remove-sm" onclick={() => removeItem("todo", todo)} title="Remove">✕</button>
        </div>
      </div>
    {:else}
      <p class="empty">No todos.</p>
    {/each}

  {:else if d.entries !== undefined}
    {#if activeForm === "journal-write"}
      <div class="modal-overlay" onclick={closeForm} onkeydown={(e) => e.key === "Escape" && closeForm()} role="button" tabindex="-1" aria-label="Dismiss">
        <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
          <div class="modal-header">
            <h2>Write Journal Entry</h2>
          </div>
          <div class="form">
            <label class="field">
              <span class="field-label">Title *</span>
              <input type="text" class="text-input" bind:value={journalTitle} placeholder="Entry title" autofocus />
            </label>
            <label class="field">
              <span class="field-label">Date</span>
              <input type="date" class="text-input" bind:value={journalDate} />
            </label>
            <label class="field">
              <span class="field-label">Content</span>
              <textarea class="text-input textarea journal-textarea" bind:value={journalText} rows="10" placeholder="Write your journal entry here..."></textarea>
            </label>
            {#if journalError}
              <p class="error">{journalError}</p>
            {/if}
            <div class="form-actions">
              <button class="btn-primary" onclick={handleSaveJournal} disabled={savingJournal || !journalTitle.trim()}>
                {savingJournal ? "Saving…" : "Save Entry"}
              </button>
              <button class="btn-secondary" onclick={closeForm}>Cancel</button>
            </div>
          </div>
        </div>
      </div>
    {/if}
    <div class="section-header">
      <h3 class="title">Journal Entries</h3>
      <button class="btn-add" onclick={() => { resetJournalForm({}); openForm("journal-write"); }}>+ Write Entry</button>
    </div>
    {#each d.entries as entry}
      <div class="row">
        <span class="key">{entry.uuid?.slice(0, 8) || ""}</span>
        <span class="val">{(entry.titolo || entry.title || "").slice(0, 32)}</span>
        <span class="hint">{entry.dato || entry.date || ""}</span>
        <div class="row-actions">
          <button class="btn-remove-sm" onclick={() => removeItem("journal", entry)} title="Remove">✕</button>
        </div>
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
    height: 100%;
    overflow-y: auto;
  }
  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
    padding: 0.75rem 0.75rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
  }
  .title {
    font-size: 0.95rem;
    color: #e0e0e0;
    font-weight: 600;
  }
  .btn-add {
    background: #2a4a2a;
    color: #b0d0b0;
    border: 1px solid #3a6a3a;
    border-radius: 6px;
    padding: 0.35rem 0.75rem;
    font-family: monospace;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-add:hover {
    background: #3a6a3a;
  }
  .row {
    display: flex;
    gap: 0.5rem;
    padding: 0.3rem 0.75rem;
    border-bottom: 1px solid #2a2a3e;
    align-items: center;
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
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .hint {
    color: var(--clr-muted);
    flex-shrink: 0;
  }
  .row-actions {
    flex-shrink: 0;
    margin-left: 0.5rem;
  }
  .btn-remove-sm {
    background: transparent;
    border: 1px solid #4a2a2a;
    color: #8a4a4a;
    border-radius: 4px;
    padding: 0.1rem 0.35rem;
    font-size: 0.7rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-remove-sm:hover {
    background: #4a2a2a;
    color: #d0a0a0;
  }
  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }
  .message {
    color: #e0e0e0;
    white-space: pre-wrap;
    padding: 0.75rem;
  }
  /* Modal overlay (shared with existing form modals) */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 500;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: fadeIn 0.15s ease;
  }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  .modal {
    background: #1e1e32;
    border: 1px solid #444;
    border-radius: 16px;
    padding: 1.5rem;
    width: 420px;
    max-width: 90vw;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
  }
  .modal-header { margin-bottom: 1rem; }
  .modal-header h2 { font-size: 1.1rem; color: #e0e0e0; font-weight: 600; }
  .form { display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.3rem; }
  .field-label { font-size: 0.78rem; color: #7c7c9a; font-family: monospace; }
  .text-input {
    background: #2a2a3e;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 0.5rem 0.7rem;
    color: #e0e0e0;
    font-size: 0.85rem;
    outline: none;
    font-family: monospace;
  }
  .text-input:focus { border-color: #7c7c9a; }
  .textarea {
    resize: vertical;
    min-height: 60px;
    line-height: 1.4;
  }
  .journal-textarea {
    min-height: 200px;
  }
  .row-fields { display: flex; gap: 0.75rem; }
  .row-fields .field { flex: 1; }
  .error { color: #aa6a6a; font-size: 0.8rem; }
  .form-actions { display: flex; gap: 0.5rem; margin-top: 0.25rem; }
  .btn-primary, .btn-secondary {
    padding: 0.45rem 1rem;
    border-radius: 8px;
    border: 1px solid #444;
    font-family: monospace;
    font-size: 0.85rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-primary {
    background: #3a6a3a;
    color: #e0e0e0;
    border-color: #4a8a4a;
    flex: 1;
  }
  .btn-primary:hover { background: #4a8a4a; }
  .btn-primary:disabled { opacity: 0.4; cursor: default; }
  .btn-secondary { background: #2a2a3e; color: #b0b0c0; }
  .btn-secondary:hover { background: #3a3a5a; }
</style>
