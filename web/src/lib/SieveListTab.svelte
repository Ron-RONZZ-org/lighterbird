<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi, sieve as sieveApi } from "./api.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";

  let { data = {} } = $props();
  let scripts = $derived(data?.scripts || []);
  let total = $derived(data?.total || 0);

  let selectionMode = $state(false);
  let selectedNames = $state(new Set());
  let focusedIndex = $state(-1);

  let accountFilter = $state("");
  let confirmDelete = $state(false);
  let deleteTarget = $state("");

  let numSelected = $derived(selectedNames.size);

  // Load accounts for filter
  let accounts = $state([]);
  $effect(() => {
    emailApi.listAccounts().then((r) => {
      accounts = r?.accounts || [];
    }).catch(() => {});
  });

  function toggleSelectionMode() {
    selectionMode = !selectionMode;
    if (!selectionMode) {
      selectedNames = new Set();
      focusedIndex = -1;
    } else if (scripts.length > 0 && focusedIndex === -1) {
      focusedIndex = 0;
    }
  }

  function toggleScript(name) {
    const next = new Set(selectedNames);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    selectedNames = next;
  }

  function isSelected(name) {
    return selectedNames.has(name);
  }

  function openEditor(script) {
    tabStore.open("sieve-editor", `Edit: ${script.name}`, { script, accounts, accountFilter }, {
      idKey: `sieve-${script.name}`,
    });
  }

  function addNew() {
    tabStore.open("sieve-editor", "New Sieve Script", { script: null, accounts, accountFilter }, {
      idKey: "sieve-new",
    });
  }

  async function deleteScript(name) {
    try {
      await sieveApi.delete(name, accountFilter);
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Delete Failed", { message: err.message || "Failed to delete script" });
    }
  }

  async function deleteSelected() {
    const names = [...selectedNames];
    if (names.length === 0) return;
    try {
      for (const name of names) {
        await sieveApi.delete(name, accountFilter);
      }
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Delete Failed", { message: err.message || "Failed to delete scripts" });
    }
  }

  async function activateScript(name) {
    try {
      await sieveApi.activate(name, accountFilter);
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Activate Failed", { message: err.message || "Failed to activate script" });
    }
  }

  async function refreshList() {
    try {
      const result = await sieveApi.list(accountFilter);
      tabStore.update(tabStore.active.id, result);
      selectedNames = new Set();
    } catch { /* silent */ }
  }

  function handleAccountChange(e) {
    accountFilter = e.target.value;
    refreshList();
  }

  function handleRowClick(name) {
    if (selectionMode) {
      toggleScript(name);
    } else {
      const script = scripts.find((s) => s.name === name);
      if (script) openEditor(script);
    }
  }

  function truncate(s, max) {
    if (!s) return "";
    return s.length > max ? s.slice(0, max - 1) + "…" : s;
  }
</script>

<div class="sieve-list">
  <!-- Toolbar -->
  <div class="toolbar">
    <div class="left">
      <button class="btn" onclick={addNew} title="Create new Sieve script">+ New</button>
      <button class="btn" onclick={toggleSelectionMode} title="Toggle multi-select mode">
        {selectionMode ? "Done" : "Select"}
      </button>
      {#if selectionMode && numSelected > 0}
        <button class="btn danger" onclick={deleteSelected}>Delete ({numSelected})</button>
      {/if}
      <button class="btn" onclick={refreshList} title="Refresh list">⟳</button>
    </div>
    <div class="right">
      <select class="account-select" onchange={handleAccountChange} value={accountFilter}>
        <option value="">All accounts</option>
        {#each accounts as acct}
          <option value={acct.uuid}>{acct.email}</option>
        {/each}
      </select>
    </div>
  </div>

  <!-- Script list -->
  <div class="list" role="listbox" aria-label="Sieve scripts">
    {#each scripts as script, i (script.name)}
      <div
        class="row"
        class:selected={isSelected(script.name)}
        class:system={script.system}
        class:selection-mode={selectionMode}
        role="option"
        aria-selected={isSelected(script.name)}
        tabindex={selectionMode ? (i === focusedIndex ? 0 : -1) : 0}
        onclick={() => handleRowClick(script.name)}
        onkeydown={(e) => { if (e.key === "Enter") handleRowClick(script.name); }}
      >
        <span class="checkbox-cell">
          {#if selectionMode}
            <span class="checkbox" class:checked={isSelected(script.name)}>
              {isSelected(script.name) ? "✓" : ""}
            </span>
          {/if}
        </span>
        <span class="name" class:active={script.active}>
          {script.system ? "⚙ " : ""}{script.name}
        </span>
        <span class="status-badge" class:active={script.active}>
          {script.active ? "ACTIVE" : ""}
        </span>
        <span class="meta">
          {#if script.system}
            <span class="tag system">system</span>
          {/if}
          {#if script.man_sync}
            <span class="tag sync">sync</span>
          {/if}
        </span>
        <span class="actions">
          {#if !script.system}
            <button class="btn small" onclick={(e) => { e.stopPropagation(); activateScript(script.name); }}
              title="Activate this script">★ Activate</button>
            <button class="btn small" onclick={(e) => { e.stopPropagation(); openEditor(script); }}
              title="Edit script">✎ Edit</button>
            <button class="btn small danger" onclick={(e) => { e.stopPropagation(); deleteTarget = script.name; confirmDelete = true; }}
              title="Delete script">✕</button>
          {/if}
        </span>
      </div>
    {:else}
      <p class="empty">No Sieve scripts. Create one with <strong>!email sieve add</strong>.</p>
    {/each}
  </div>
</div>

{#if confirmDelete}
  <ConfirmDialog
    message="Delete script '{deleteTarget}'?"
    onConfirm={async () => { confirmDelete = false; await deleteScript(deleteTarget); }}
    onDismiss={() => { confirmDelete = false; }}
  />
{/if}

<style>
  .sieve-list {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-family: monospace;
    font-size: 0.85rem;
    background: #1a1a2e;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
    gap: 0.5rem;
    flex-shrink: 0;
  }
  .left, .right {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  .btn {
    padding: 0.2rem 0.5rem;
    border: 1px solid #4a4a6a;
    border-radius: 3px;
    background: #2a2a44;
    color: #ccc;
    font-family: monospace;
    font-size: 0.78rem;
    cursor: pointer;
    white-space: nowrap;
  }
  .btn:hover { background: #3a3a5a; }
  .btn.danger { border-color: #8a3a3a; color: #e07070; }
  .btn.danger:hover { background: #3a2020; }
  .btn.small { padding: 0.1rem 0.3rem; font-size: 0.72rem; }
  .account-select {
    padding: 0.15rem 0.3rem;
    border: 1px solid #4a4a6a;
    border-radius: 3px;
    background: #2a2a44;
    color: #ccc;
    font-family: monospace;
    font-size: 0.78rem;
  }
  .list {
    flex: 1;
    overflow-y: auto;
    padding: 0;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.35rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
    cursor: default;
    min-height: 2rem;
    transition: background 0.08s;
  }
  .row:hover { background: #2a2a44; }
  .row.selected { background: #2a2a50; }
  .row.system { opacity: 0.8; }
  .row.selection-mode { cursor: pointer; }
  .checkbox-cell {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 1.8rem;
    flex-shrink: 0;
  }
  .checkbox {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.1rem;
    height: 1.1rem;
    border: 1.5px solid #7c7c9a;
    border-radius: 3px;
    font-size: 0.7rem;
    color: #e0e0e0;
    background: transparent;
  }
  .checkbox.checked { background: #4a6fa5; border-color: #4a6fa5; }
  .name {
    flex: 1;
    color: #e0e0e0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .name.active { font-weight: 700; color: #7fdb7f; }
  .status-badge {
    font-size: 0.65rem;
    padding: 1px 5px;
    border-radius: 3px;
    color: #555;
    flex-shrink: 0;
  }
  .status-badge.active {
    background: #1e3a1e;
    color: #7fdb7f;
    border: 1px solid #2a5a2a;
  }
  .meta {
    display: flex;
    gap: 0.3rem;
    flex-shrink: 0;
  }
  .tag {
    font-size: 0.62rem;
    padding: 1px 4px;
    border-radius: 3px;
  }
  .tag.system { background: #3a2a1e; color: #dba87f; }
  .tag.sync { background: #1e2a3a; color: #7fa8db; }
  .actions {
    display: flex;
    gap: 0.3rem;
    flex-shrink: 0;
  }
  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }
</style>
