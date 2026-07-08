<script>
  import AccountList from "./AccountList.svelte";
  import LlmProfileForm from "./LlmProfileForm.svelte";
  import EmailAccountForm from "./EmailAccountForm.svelte";
  import CalendarAccountForm from "./CalendarAccountForm.svelte";
  import BackupStrategyList from "./BackupStrategyList.svelte";
  import BackupStrategyForm from "./BackupStrategyForm.svelte";

  let {
    data = {},
    activeForm = null,
    editingItem = null,
    testingStrategies = new Set(),
    testResults = {},
    onOpenForm = () => {},
    onCloseForm = () => {},
    onRemoveItem = () => {},
    onActivateProfile = () => {},
    onTestStrategy = () => {},
    onRefetch = () => {},
    onSaveJournal = () => {},
    onOpenSignatureAdd = () => {},
    onOpenSignatureModify = () => {},
    onDeleteSignature = () => {},
    onOpenJournalWrite = () => {},
    onOpenUserProfileAdd = () => {},
    onRecallDraft = () => {},
    onDeleteDraft = () => {},
  } = $props();

  let d = $derived(data || {});
</script>

<div class="status">
  {#if d.accounts !== undefined}
    {#if activeForm === "email"}
      <EmailAccountForm
        account={editingItem?.uuid ? editingItem : null}
        initialData={!editingItem?.uuid ? editingItem : null}
        onSaved={() => { onCloseForm(); onRefetch(); }}
        onDismiss={onCloseForm}
      />
    {/if}
    <AccountList
      type="email"
      items={d.accounts}
      onAdd={() => onOpenForm("email")}
      onModify={(item) => onOpenForm("email", item)}
      onRemove={(item) => onRemoveItem("email", item)}
    />

  {:else if d.calendars !== undefined}
    {#if activeForm === "calendar"}
      <CalendarAccountForm
        calendar={editingItem?.uuid ? editingItem : null}
        initialData={!editingItem?.uuid ? editingItem : null}
        onSaved={() => { onCloseForm(); onRefetch(); }}
        onDismiss={onCloseForm}
      />
    {/if}
    <AccountList
      type="calendar"
      items={d.calendars}
      onAdd={() => onOpenForm("calendar")}
      onModify={(item) => onOpenForm("calendar", item)}
      onRemove={(item) => onRemoveItem("calendar", item)}
    />

  {:else if d.profiles !== undefined}
    {#if activeForm === "llm"}
      <LlmProfileForm
        profile={editingItem}
        onSaved={() => { onCloseForm(); onRefetch(); }}
        onDismiss={onCloseForm}
      />
    {/if}
    <AccountList
      type="llm"
      items={d.profiles}
      activeName={d.active_profile || ""}
      onAdd={() => onOpenForm("llm")}
      onModify={(item) => onOpenForm("llm", item)}
      onRemove={(item) => onRemoveItem("llm", item)}
      onActivate={(item) => onActivateProfile(item)}
    />

  {:else if d.strategies !== undefined}
    {#if activeForm === "backup-strategy"}
      <BackupStrategyForm
        strategy={editingItem}
        onSaved={() => { onCloseForm(); onRefetch(); }}
        onDismiss={onCloseForm}
      />
    {/if}
    <BackupStrategyList
      items={d.strategies}
      {testingStrategies}
      {testResults}
      onAdd={() => onOpenForm("backup-strategy")}
      onModify={(item) => onOpenForm("backup-strategy", item)}
      onRemove={(item) => onRemoveItem("backup-strategy", item)}
      onTest={(item) => onTestStrategy(item)}
    />

  {:else if d.signatures !== undefined}
    <div class="section-header">
      <h3 class="title">Email Signatures</h3>
      <button class="btn-add" onclick={onOpenSignatureAdd}>+ Add Signature</button>
    </div>
    {#each d.signatures as sig}
      <div class="row">
        <span class="key">{sig.name || "default"}</span>
        <span class="hint">{#if sig.default_for}{sig.default_for.join(", ")}{/if}</span>
        <span class="val" title={sig.signature_text || sig.signature || ""}>
          {(sig.signature_text || sig.signature || "").length > 60
            ? (sig.signature_text || sig.signature || "").slice(0, 60) + "\u2026"
            : (sig.signature_text || sig.signature || "(no signature)")}
        </span>
        <div class="row-actions">
          <button class="btn-modify-sm" onclick={() => onOpenSignatureModify(sig)} title="Edit">&#x270E;</button>
          <button class="btn-remove-sm" onclick={() => onDeleteSignature(sig)} title="Remove">&#x2715;</button>
        </div>
      </div>
    {:else}
      <p class="empty">No signatures configured.</p>
    {/each}

  {:else if d.entries !== undefined}
    <div class="section-header">
      <h3 class="title">Journal Entries</h3>
      <button class="btn-add" onclick={onOpenJournalWrite}>+ Write Entry</button>
    </div>
    {#each d.entries as entry}
      <div class="row">
        <span class="key">{entry.uuid?.slice(0, 8) || ""}</span>
        <span class="val">{(entry.titolo || entry.title || "").slice(0, 32)}</span>
        <span class="hint">{entry.dato || entry.date || ""}</span>
        <div class="row-actions">
          <button class="btn-remove-sm" onclick={() => onRemoveItem("journal", entry)} title="Remove">&#x2715;</button>
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
          <button class="btn-modify-sm" onclick={() => onRecallDraft(draft)} title="Recall / Edit">&#x270E;</button>
          <button class="btn-remove-sm" onclick={() => onDeleteDraft(draft)} title="Remove">&#x2715;</button>
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

  {:else if d.user_profiles !== undefined}
    <div class="section-header">
      <h3 class="title">User Profiles ({d.user_profiles.length})</h3>
      <button class="btn-add" onclick={onOpenUserProfileAdd}>+ Add Profile</button>
    </div>
    {#each d.user_profiles as p}
      <div class="row">
        <span class="key">{p.uuid || ""}</span>
        <span class="val">{(p.profile_name || "") + (p.full_name ? " \u2014 " + p.full_name : "")}</span>
        <span class="hint">{p.primary_email || p.organization || ""}</span>
      </div>
    {:else}
      <p class="empty">No profiles.</p>
    {/each}

  {:else if d.templates !== undefined}
    <div class="section-header">
      <h3 class="title">Todo Templates ({d.templates.length})</h3>
    </div>
    {#each d.templates as t}
      <div class="row">
        <span class="key">{t.uuid ? t.uuid.slice(0, 8) : ""}</span>
        <span class="val">{t.name || ""}</span>
        <span class="hint">{t.field_count ? t.field_count + " fields" : ""}</span>
      </div>
    {:else}
      <p class="empty">No templates.</p>
    {/each}

  {:else if d.scripts !== undefined}
    <div class="section-header">
      <h3 class="title">Sieve Scripts ({d.scripts.length})</h3>
    </div>
    {#each d.scripts as s}
      <div class="row">
        <span class="key">{s.name || ""}</span>
        <span class="val">{s.size ? s.size + " bytes" : ""}</span>
        <span class="hint">{(s.active ? "\u2713 active" : "") + (s.accounts ? " (" + s.accounts + ")" : "")}</span>
      </div>
    {:else}
      <p class="empty">No sieve scripts.</p>
    {/each}

  {:else}
    {#each Object.entries(d) as [key, val]}
      {#if typeof val === "string" && val}
        <div class="row">
          <span class="key">{key}</span>
          <span class="val">{val}</span>
        </div>
      {:else if typeof val === "number"}
        <div class="row">
          <span class="key">{key}</span>
          <span class="val">{val}</span>
        </div>
      {:else if typeof val === "boolean"}
        <div class="row">
          <span class="key">{key}</span>
          <span class="val">{val ? "\u2713" : "\u2014"}</span>
        </div>
      {:else if Array.isArray(val) && val.length > 0}
        <div class="row">
          <span class="key">{key}</span>
          <span class="val">{val.length} item{val.length !== 1 ? "s" : ""}</span>
        </div>
      {/if}
    {/each}
    {#if Object.keys(d).length === 0}
      <p class="message">No data.</p>
    {/if}
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
</style>
