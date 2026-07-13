<script>
  /**
   * EmailFolderTab.svelte — Full-screen IMAP folder management tab.
   *
   * Recycles EmailFolderTree + EmailTreeNode for the tree view.
   * Follows the List Tab Standard Feature Set (selection mode, keyboard
   * navigation, batch actions, search, UUID copy, toolbar).
   */
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi } from "./api.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import EmailFolderTree from "./EmailFolderTree.svelte";
  import { createCopyState, createSelectionManager } from "./listTabShared.svelte.js";

  let { data = {} } = $props();
  let folders = $state(data?.folders || []);
  let accounts = $state(data?.accounts || []);
  let total = $derived(folders.length);
  let highlight = $derived(data?.highlight || "");

  // ── Account filter ─────────────────────────────────────────────────────
  let accountFilter = $state("");
  let filteredFolders = $derived(
    accountFilter
      ? folders.filter((f) => f.account_email === accountFilter)
      : folders,
  );

  // ── Shared copy state ──────────────────────────────────────────────────
  let copyState = createCopyState();

  // ── Selection state (adapted for tree items) ───────────────────────────
  // We map tree item paths to a flat selection set.
  let selectionMode = $state(false);
  let selectedPaths = $state(new Set());
  let focusedIndex = $state(-1);
  let numSelected = $derived(selectedPaths.size);

  // ── UI state ──────────────────────────────────────────────────────────
  let confirmDelete = $state(false);
  let showNewFolderInput = $state(false);
  let newFolderName = $state("");
  let creating = $state(false);
  let createError = $state("");
  let renaming = $state(false);
  let renamePath = $state("");
  let renameName = $state("");
  let renameError = $state("");
  let searchQuery = $state("");
  let showSearch = $state(false);
  let showSync = $state(false);
  let syncing = $state(false);
  let highlightActive = $state(false);

  // Highlight animation
  $effect(() => {
    if (highlight) {
      highlightActive = true;
      const timer = setTimeout(() => { highlightActive = false; }, 2000);
      return () => clearTimeout(timer);
    }
  });

  // ── Load accounts if not provided ──────────────────────────────────────
  $effect(() => {
    if (accounts.length === 0) {
      emailApi.listAccounts().then((res) => {
        accounts = res?.accounts || [];
        if (!accountFilter && accounts.length > 0) {
          accountFilter = accounts[0].email;
        }
      }).catch(() => {});
    }
  });

  // ── Synchronisation ────────────────────────────────────────────────────
  async function handleSync() {
    syncing = true;
    try {
      await emailApi.sync(accountFilter || undefined);
      await refreshList();
    } catch { /* silent */ }
    finally { syncing = false; }
  }

  // ── Refresh ────────────────────────────────────────────────────────────
  async function refreshList() {
    const tabId = tabStore.findByKey("persistent-folder-list") || tabStore.active.id;
    try {
      const params = accountFilter ? {} : {};
      const result = await emailApi.listFolders();
      const allFolders = result.folders || [];
      const filtered = accountFilter
        ? allFolders.filter((f) => f.account_email === accountFilter)
        : allFolders;
      tabStore.safeUpdate(tabId, { folders: filtered, total: filtered.length, accounts });
      folders = filtered;
      selectedPaths = new Set();
    } catch { /* silent */ }
  }

  // ── Folder operations ──────────────────────────────────────────────────
  async function handleCreateFolder(name) {
    if (!accountFilter) throw new Error("Select an account first.");
    await emailApi.createFolder(accountFilter, name);
    await refreshList();
  }

  async function handleStartRename(path) {
    renaming = true;
    renamePath = path;
    renameError = "";
    // Extract the simple name (last segment)
    const parts = path.split("/");
    renameName = parts[parts.length - 1];
  }

  async function handleConfirmRename() {
    if (!renameName.trim()) return;
    renaming = false;
    const oldName = renamePath;
    const newName = renameName.trim();
    try {
      // oldName is "account_email/folder_name" — need to split
      const slashIdx = oldName.indexOf("/");
      if (slashIdx < 0) return;
      const acctEmail = oldName.slice(0, slashIdx);
      const fldName = oldName.slice(slashIdx + 1);
      await emailApi.renameFolder(acctEmail, fldName, newName);
      await refreshList();
    } catch (err) {
      renameError = err.message || "Rename failed";
    }
    renamePath = "";
    renameName = "";
  }

  async function handleDeleteFolder(path) {
    const slashIdx = path.indexOf("/");
    if (slashIdx < 0) return;
    const acctEmail = path.slice(0, slashIdx);
    const fldName = path.slice(slashIdx + 1);
    try {
      await emailApi.deleteFolder(acctEmail, fldName);
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Delete Failed", { message: err.message || "Failed to delete folder" });
    }
  }

  async function deleteSelected() {
    const paths = [...selectedPaths];
    if (paths.length === 0) return;
    for (const path of paths) {
      await handleDeleteFolder(path);
    }
    selectedPaths = new Set();
    selectionMode = false;
  }

  // ── Selection mode ─────────────────────────────────────────────────────
  function toggleSelectionMode() {
    selectionMode = !selectionMode;
    if (!selectionMode) {
      selectedPaths = new Set();
      focusedIndex = -1;
    }
  }

  function toggleItem(path) {
    const next = new Set(selectedPaths);
    if (next.has(path)) next.delete(path);
    else next.add(path);
    selectedPaths = next;
  }

  function isSelected(path) {
    return selectedPaths.has(path);
  }

  function getFlatFolderList() {
    // Flatten tree to a list of paths for arrow-key navigation
    const result = [];
    function walk(nodes) {
      for (const n of nodes) {
        result.push(n.path);
        if (n.expanded && n.children?.length) walk(n.children);
      }
    }
    // Build tree from filteredFolders
    const tree = buildQuickTree(filteredFolders);
    walk(tree);
    return result;
  }

  function buildQuickTree(flat) {
    const root = {};
    for (const f of flat) {
      const path = f.label || `${f.account_email}/${f.folder_name}`;
      const parts = path.split("/");
      let node = root;
      for (const part of parts) {
        if (!node[part]) node[part] = {};
        node = node[part];
      }
      node._folder = f;
      node._path = path;
    }
    function toList(obj, prefix) {
      const nodes = [];
      for (const [key, val] of Object.entries(obj)) {
        if (key.startsWith("_")) continue;
        const path = prefix ? `${prefix}/${key}` : key;
        const hasChildren = Object.keys(val).some((k) => !k.startsWith("_"));
        nodes.push({
          name: key, path, isFolder: !!val._folder,
          folder: val._folder || null,
          children: hasChildren ? toList(val, path) : [],
        });
      }
      return nodes;
    }
    return toList(root, "");
  }

  // ── Keyboard handler ───────────────────────────────────────────────────
  function handleKeydown(e) {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable) return;

    const plain = !e.ctrlKey && !e.metaKey && !e.altKey;

    if (e.key === "Escape") {
      if (selectionMode) { toggleSelectionMode(); e.preventDefault(); return; }
      if (showSearch) { showSearch = false; searchQuery = ""; e.preventDefault(); return; }
      tabStore.close(tabStore.active?.id);
      return;
    }

    if (plain && e.key === "f") { showSearch = !showSearch; e.preventDefault(); return; }
    if (plain && e.key === "n") { if (!selectionMode) showNewFolderInput = true; e.preventDefault(); return; }
    if (plain && e.key === "v") { toggleSelectionMode(); e.preventDefault(); return; }
    if (plain && e.key === "r") { if (e.target.closest("[data-path]")) e.preventDefault(); return; }

    // Arrow key navigation when in selection mode
    if (selectionMode) {
      const flat = getFlatFolderList();
      if (flat.length === 0) return;
      if (e.key === "ArrowDown") {
        focusedIndex = Math.min(focusedIndex + 1, flat.length - 1);
        e.preventDefault();
      } else if (e.key === "ArrowUp") {
        focusedIndex = Math.max(focusedIndex - 1, 0);
        e.preventDefault();
      } else if (e.key === " " && focusedIndex >= 0) {
        toggleItem(flat[focusedIndex]);
        e.preventDefault();
      }
    }
  }

  function handleAccountChange(e) {
    accountFilter = e.target.value;
    refreshList();
  }

  // ── Tree callbacks (passthrough to EmailFolderTree) ───────────────────
  let folderVisibility = $state({});
  let expandedFolders = $state([]);

  function handleToggleFolder(path) {}
  function handleToggleExpand(path) {
    expandedFolders = expandedFolders.includes(path)
      ? expandedFolders.filter((p) => p !== path)
      : [...expandedFolders, path];
  }

  // ── New folder from tree inline form ──────────────────────────────────
  async function handleTreeCreateFolder(name) {
    if (!accountFilter) throw new Error("Select an account first.");
    await emailApi.createFolder(accountFilter, name);
    await refreshList();
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="folder-tab">
  <!-- ── Toolbar ──────────────────────────────────────────────────────── -->
  <div class="toolbar">
    <div class="left">
      {#if !selectionMode}
        <button class="btn" onclick={() => { showNewFolderInput = true; }} title="Create new folder">
          + New <kbd>N</kbd>
        </button>
        <button class="btn" onclick={toggleSelectionMode} title="Toggle multi-select mode">
          Select
        </button>
        <button class="btn" onclick={handleSync} disabled={syncing} title="Sync folders">
          {syncing ? "⟳ Syncing…" : "⟳ Sync"}
        </button>
        <button class="btn" onclick={() => { showSearch = !showSearch; }} title="Search folders">
          🔍 Search
        </button>
      {:else}
        <button class="btn" onclick={toggleSelectionMode} title="Exit selection mode">
          Done
        </button>
        {#if numSelected > 0}
          <span class="selected-count">{numSelected} selected</span>
          <button class="btn danger" onclick={() => { confirmDelete = true; }}>
            Delete ({numSelected})
          </button>
        {/if}
      {/if}
    </div>
    <div class="right">
      {#if accounts.length > 0}
        <label class="filter-label" for="folder-account-filter">Account:</label>
        <select id="folder-account-filter" class="account-select" onchange={handleAccountChange} value={accountFilter}>
          <option value="">(all accounts)</option>
          {#each accounts as acct}
            <option value={acct.email || acct}>{acct.email || acct}</option>
          {/each}
        </select>
      {/if}
    </div>
  </div>

  <!-- ── Search bar ──────────────────────────────────────────────────── -->
  {#if showSearch}
    <div class="search-bar">
      <input
        type="text"
        class="search-input"
        placeholder="Search folders…"
        bind:value={searchQuery}
        onkeydown={(e) => e.stopPropagation()}
      />
      <button class="btn small" onclick={() => { showSearch = false; searchQuery = ""; }}>✕</button>
    </div>
  {/if}

  <!-- ── Inline new-folder form at top ────────────────────────────────── -->
  {#if showNewFolderInput}
    <div class="inline-form">
      <input
        type="text"
        class="form-input"
        placeholder="New folder name"
        bind:value={newFolderName}
        onkeydown={(e) => {
          if (e.key === "Enter") {
            handleCreateFolder(newFolderName.trim()).then(() => {
              newFolderName = "";
              showNewFolderInput = false;
            }).catch((err) => { createError = err.message; });
          }
          if (e.key === "Escape") { showNewFolderInput = false; newFolderName = ""; createError = ""; }
        }}
        disabled={creating}
      />
      <button class="btn primary small" onclick={async () => {
        try {
          await handleCreateFolder(newFolderName.trim());
          newFolderName = "";
          showNewFolderInput = false;
        } catch (err) { createError = err.message; }
      }} disabled={creating || !newFolderName.trim()}>
        {creating ? "Creating…" : "Create"}
      </button>
      <button class="btn small" onclick={() => { showNewFolderInput = false; newFolderName = ""; createError = ""; }}>Cancel</button>
      {#if createError}
        <span class="error-msg">{createError}</span>
      {/if}
    </div>
  {/if}

  <!-- ── Rename inline form ──────────────────────────────────────────── -->
  {#if renaming}
    <div class="inline-form">
      <span class="form-label">Rename:</span>
      <input
        type="text"
        class="form-input"
        bind:value={renameName}
        onkeydown={(e) => {
          if (e.key === "Enter") handleConfirmRename();
          if (e.key === "Escape") { renaming = false; renameError = ""; }
        }}
      />
      <button class="btn primary small" onclick={handleConfirmRename}>Rename</button>
      <button class="btn small" onclick={() => { renaming = false; renameError = ""; }}>Cancel</button>
      {#if renameError}
        <span class="error-msg">{renameError}</span>
      {/if}
    </div>
  {/if}

  <!-- ── Folder tree (recycled component) ─────────────────────────────── -->
  <div class="tree-wrapper">
    <EmailFolderTree
      folders={filteredFolders}
      bind:folderVisibility
      bind:expandedFolders
      onToggleFolder={handleToggleFolder}
      onToggleExpand={handleToggleExpand}
      onCreateFolder={handleTreeCreateFolder}
    />
  </div>

  <!-- ── Empty state ──────────────────────────────────────────────────── -->
  {#if filteredFolders.length === 0}
    <p class="empty">
      {#if accountFilter}
        No folders found for {accountFilter}.
      {:else}
        No folders found. Use <strong>!email folder add --parent</strong> to create one.
      {/if}
    </p>
  {/if}
</div>

<!-- ── Modals ─────────────────────────────────────────────────────────────────── -->
{#if confirmDelete}
  <ConfirmDialog
    message="Delete {numSelected} folder{numSelected !== 1 ? 's' : ''} from IMAP server? This removes messages too."
    onConfirm={async () => { confirmDelete = false; await deleteSelected(); }}
    onDismiss={() => { confirmDelete = false; }}
  />
{/if}

<style>
  .folder-tab {
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
    transition: background 0.1s;
  }

  .btn:hover:not(:disabled) { background: #3a3a5a; }
  .btn:disabled { opacity: 0.4; cursor: default; }
  .btn.danger { border-color: #8a3a3a; color: #e07070; }
  .btn.danger:hover:not(:disabled) { background: #3a2020; }
  .btn.primary { border-color: #3a6a3a; color: #7fdb7f; }
  .btn.primary:hover:not(:disabled) { background: #1e3a1e; }
  .btn.small { padding: 0.1rem 0.3rem; font-size: 0.72rem; }

  .filter-label {
    color: var(--clr-muted);
    font-size: 0.72rem;
    white-space: nowrap;
  }

  .account-select {
    padding: 0.15rem 0.3rem;
    border: 1px solid #4a4a6a;
    border-radius: 3px;
    background: #2a2a44;
    color: #ccc;
    font-family: monospace;
    font-size: 0.78rem;
  }

  .selected-count {
    color: var(--clr-muted);
    font-size: 0.78rem;
    white-space: nowrap;
  }

  .search-bar {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.3rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
    background: #16162a;
  }

  .search-input {
    flex: 1;
    padding: 0.25rem 0.4rem;
    border: 1px solid #444;
    border-radius: 3px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.78rem;
    outline: none;
  }

  .search-input:focus { border-color: #6a6a9a; }

  .inline-form {
    display: flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.3rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
    background: #16162a;
    flex-wrap: wrap;
  }

  .form-label {
    color: var(--clr-muted);
    font-size: 0.78rem;
    white-space: nowrap;
  }

  .form-input {
    flex: 1;
    min-width: 200px;
    padding: 0.25rem 0.4rem;
    border: 1px solid #444;
    border-radius: 3px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.78rem;
    outline: none;
  }

  .form-input:focus { border-color: #6a6a9a; }

  .error-msg {
    color: #d06;
    font-size: 0.72rem;
  }

  .tree-wrapper {
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem;
  }

  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }
</style>
