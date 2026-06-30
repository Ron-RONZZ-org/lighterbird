<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { calendar as calendarApi, llm as llmApi, email as emailApi, drafts as draftsApi } from "./api.js";
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
      } else if (d.signatures !== undefined) {
        const resp = await fetch("/api/v1/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tokens: ["email", "signature", "list"], flags: {} }),
        });
        const cmdResult = await resp.json();
        if (resp.ok) {
          result = cmdResult.data;
        }
      } else if (d.entries !== undefined) {
        result = await journalApi.list({ limit: 50 });
      }
      if (result) {
        tabStore.update(active.id, result);
      }
    } catch { /* ignore */ }
  }

  /** Save a journal entry via the journal API. */
  async function saveJournal(data) {
    await journalApi.create(data);
    closeForm();
    await refetchCurrentTab();
  }


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

  {:else if d.signatures !== undefined}
    <div class="section-header">
      <h3 class="title">Email Signatures</h3>
      <button class="btn-add" onclick={() =>
        tabStore.open("form", "Add Email Signature", {
          form: "email-signature-add",
          initialData: {},
        }, { idKey: "form-email-signature-add" })
      }>+ Add Signature</button>
    </div>
    {#each d.signatures as sig}
      <div class="row">
        <span class="key">{sig.email || ""}</span>
        <span class="val" title={sig.signature || ""}>
          {sig.signature ? (sig.signature.length > 60 ? sig.signature.slice(0, 60) + "…" : sig.signature) : "(no signature)"}
        </span>
        <span class="hint">{sig.has_signature ? "✓" : "—"}</span>
        <div class="row-actions">
          <button class="btn-modify-sm" onclick={() =>
            tabStore.open("form", "Modify Signature: " + sig.email, {
              form: "email-signature-modify",
              initialData: { email: sig.email, text: sig.signature || "" },
            }, { idKey: "form-email-signature-modify" })
          } title="Edit">✎</button>
          <button class="btn-remove-sm" onclick={async () => {
            if (!confirm(`Delete signature for ${sig.email}?`)) return;
            try {
              const resp = await fetch("/api/v1/command", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ tokens: ["email", "signature", "delete", sig.email], flags: {} }),
              });
              if (resp.ok) await refetchCurrentTab();
            } catch { /* ignore */ }
          }} title="Remove">✕</button>
        </div>
      </div>
    {:else}
      <p class="empty">No signatures configured.</p>
    {/each}

  {:else if d.entries !== undefined}
    <div class="section-header">
      <h3 class="title">Journal Entries</h3>
      <button class="btn-add" onclick={() => tabStore.open("form", "Write Journal Entry", { form: "journal-write", initialData: {} }, { idKey: "journal-write" })}>+ Write Entry</button>
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

  {:else if d.drafts !== undefined}
    <div class="section-header">
      <h3 class="title">Drafts ({d.drafts.length})</h3>
    </div>
    {#each d.drafts as draft}
      <div class="row">
        <span class="key">{draft.uuid?.slice(0, 8) || ""}</span>
        <span class="val">{(draft.title || "").slice(0, 40)}</span>
        <span class="hint">{draft.updated || ""}</span>
        <div class="row-actions">
          <button class="btn-modify-sm" onclick={async () => {
            try {
              const full = await draftsApi.get(draft.uuid);
              const domain = full.domain || "";
              const formType = domain === "email" ? "email-send"
                : domain === "journal" ? "journal-write"
                : domain === "todo" ? "todo-add"
                : domain === "calendar-event" ? "calendar-event-add"
                : null;
              if (formType) {
                tabStore.open("form", "Recall: " + (full.title || ""), {
                  form: formType,
                  initialData: { ...full.data, _draft_uuid: full.uuid },
                }, { idKey: `form-${formType}` });
              }
            } catch { /* ignore */ }
          }} title="Recall / Edit">✎</button>
          <button class="btn-remove-sm" onclick={async () => {
            if (!confirm("Delete this draft?")) return;
            try {
              await draftsApi.delete(draft.uuid);
              // Refresh tab by re-executing command
              const active = tabStore.active;
              if (active) {
                const resp = await fetch("/api/v1/command", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ tokens: active.idKey ? active.idKey.split("-") : [], flags: {} }),
                });
                if (resp.ok) {
                  const result = await resp.json();
                  tabStore.update(active.id, result.data || {});
                }
              }
            } catch { /* ignore */ }
          }} title="Remove">✕</button>
        </div>
      </div>
    {:else}
      <p class="empty">No drafts.</p>
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
  .btn-modify-sm {
    background: transparent;
    border: 1px solid #3a5a7a;
    color: #8ab0d0;
    border-radius: 4px;
    padding: 0.1rem 0.35rem;
    font-size: 0.7rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-modify-sm:hover {
    background: #3a5a7a;
    color: #b0d0e0;
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
