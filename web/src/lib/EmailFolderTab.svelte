<script>
  /**
   * EmailFolderTab.svelte — Full-screen IMAP folder management tab.
   *
   * Features:
   * - Blocking sync-on-open with progress overlay
   * - Selection mode (V key) with checkboxes
   * - Active element tracking (click to highlight)
   * - Right-click context menu (rename/delete)
   * - Double-click to rename
   * - DELETE key to delete active folder / selected folders
   * - Drag-to-move (drop onto other folder)
   * - 2-level delete confirmation (FolderDeleteDialog)
   * - Toolbar parity with EmailListTab
   */
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi } from "./api.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import EmailFolderTree from "./EmailFolderTree.svelte";
  import SyncOverlay from "./SyncOverlay.svelte";
  import FolderContextMenu from "./FolderContextMenu.svelte";
  import FolderDeleteDialog from "./FolderDeleteDialog.svelte";
  import { createCopyState } from "./listTabShared.svelte.js";

  let { data = {} } = $props();
  let folders = $state([]);
  let accounts = $state([]);
  let total = $derived(folders.length);
  let highlight = $derived(data?.highlight || "");

  // ── Blocking sync on mount ─────────────────────────────────────────
  let initialLoading = $state(true);
  let syncing = $state(false);
  let syncTaskId = $state(null);
  let syncProgress = $state(null);
  let syncPollTimer = $state(null);
  let syncError = $state("");
  let _syncGuard = false;

  async function handleInitialSync() {
    if (_syncGuard) return;
    _syncGuard = true;
    syncing = true;
    syncProgress = null;
    syncTaskId = null;
    syncError = "";
    try {
      // Folders-only sync: register folder hierarchy without downloading messages.
      // This is fast — just an IMAP LIST per account, no message bodies.
      const startResult = await emailApi.syncStart(null, { foldersOnly: true });
      syncTaskId = startResult.task_id;
      await pollUntilComplete();
    } catch (err) {
      syncError = `Sync failed: ${err?.message || "Unknown error"}`;
      // Still need to show folders even if sync fails — load from local DB
    } finally {
      syncing = false;
      initialLoading = false;
      _syncGuard = false;
    }
    await refreshList();
  }

  function pollUntilComplete() {
    return new Promise((resolve) => {
      const poll = async () => {
        if (!syncTaskId) { resolve(); return; }
        try {
          const prog = await emailApi.getSyncProgress(syncTaskId);
          if (!prog) { resolve(); return; }
          syncProgress = prog;
          if (prog.status === "complete" || prog.status === "error") {
            if (prog.errors?.length > 0) {
              syncError = prog.errors.join("; ");
            }
            resolve();
          } else {
            syncPollTimer = setTimeout(poll, 1500);
          }
        } catch {
          resolve();
        }
      };
      syncPollTimer = setTimeout(poll, 500);
    });
  }

  function stopSync() {
    syncing = false;
    syncTaskId = null;
    syncProgress = null;
    if (syncPollTimer) { clearTimeout(syncPollTimer); syncPollTimer = null; }
  }

  // Sync from props on initial load or prop change (post-sync refresh)
  $effect(() => {
    if (data?.folders) folders = data.folders;
    if (data?.accounts) accounts = data.accounts;
  });

  // Start blocking sync on mount
  $effect(() => {
    if (initialLoading) {
      handleInitialSync();
    }
    return () => { stopSync(); };
  });

  // Highlight animation
  let highlightActive = $state(false);
  $effect(() => {
    if (highlight) {
      highlightActive = true;
      const timer = setTimeout(() => { highlightActive = false; }, 2000);
      return () => clearTimeout(timer);
    }
  });

  // ── Account filter ─────────────────────────────────────────────────
  let accountFilter = $state("");
  let filteredFolders = $derived(
    accountFilter
      ? folders.filter((f) => f.account_email === accountFilter)
      : folders,
  );

  // ── Load accounts if not provided ──────────────────────────────────
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

  // ── Shared copy state ──────────────────────────────────────────────
  let copyState = createCopyState();

  // ── Active element (single folder highlight) ───────────────────────
  let activePath = $state("");

  function handleActivate(path) {
    activePath = activePath === path ? "" : path;
  }

  // ── Selection state ────────────────────────────────────────────────
  let selectionMode = $state(false);
  let selectedPaths = $state(new Set());
  let focusedIndex = $state(-1);
  let numSelected = $derived(selectedPaths.size);

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

  // ── UI state ───────────────────────────────────────────────────────
  let showSearch = $state(false);
  let searchQuery = $state("");

  // Rename
  let renaming = $state(false);
  let renamePath = $state("");
  let renameName = $state("");
  let renameError = $state("");

  // Create (inline)
  let showNewFolderInput = $state(false);
  let newFolderName = $state("");
  let creating = $state(false);
  let createError = $state("");

  // Context menu
  let contextMenu = $state(null);  // { x, y, path } | null

  // Delete dialog
  let confirmDelete = $state(false);  // true → show FolderDeleteDialog
  let pendingDeletePaths = $state([]);

  // Flag: are we in the middle of a delete-with-disposition operation?
  let deleting = $state(false);

  // ── Refresh ────────────────────────────────────────────────────────
  async function refreshList() {
    const tabId = tabStore.findByKey("persistent-folder-list") || tabStore.active.id;
    try {
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

  // ── Folder creation ────────────────────────────────────────────────
  async function handleCreateFolder(name) {
    if (!accountFilter) throw new Error("Select an account first.");
    // If an active folder is set, use it as the parent
    const parentFlag = activePath && activePath.includes("/")
      ? activePath
      : (accountFilter || "");
    await emailApi.createFolder(accountFilter, name);
    await refreshList();
  }

  // ── Rename ─────────────────────────────────────────────────────────
  function handleStartRename(path) {
    renaming = true;
    renamePath = path;
    renameError = "";
    const parts = path.split("/");
    renameName = parts[parts.length - 1];
  }

  async function handleConfirmRename() {
    if (!renameName.trim()) return;
    renaming = false;
    const oldName = renamePath;
    const newName = renameName.trim();
    try {
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

  // ── Delete with disposition ────────────────────────────────────────
  function promptDelete(paths) {
    pendingDeletePaths = paths;
    confirmDelete = true;
  }

  async function handleDeleteWithDisposition(disposition, targetFolder) {
    confirmDelete = false;
    if (deleting) return;
    deleting = true;

    const paths = pendingDeletePaths;
    pendingDeletePaths = [];

    try {
      for (const path of paths) {
        const slashIdx = path.indexOf("/");
        if (slashIdx < 0) continue;
        const acctEmail = path.slice(0, slashIdx);
        const fldName = path.slice(slashIdx + 1);

        // Step 1: Get messages in this folder
        let msgUuids = [];
        try {
          const msgs = await emailApi.listMessages({ folder: fldName, account_email: acctEmail });
          msgUuids = (msgs.messages || []).map((m) => m.uuid);
        } catch { /* folder may be empty */ }

        // Step 2: Move messages if disposition is not "just delete"
        if (msgUuids.length > 0) {
          if (disposition === "trash") {
            try {
              // Move to Trash: we batch-trash each message
              // For efficiency, we can batch-move to a Trash folder
              // First find the Trash folder for this account
              const allFolders = (await emailApi.listFolders()).folders || [];
              const trash = allFolders.find(
                (f) => f.account_email === acctEmail &&
                  (f.folder_name?.toLowerCase() === "trash" || f.special_use === "\\Trash")
              );
              if (trash) {
                await emailApi.batchMove(msgUuids, trash.folder_name);
              }
            } catch { /* best effort */ }
          } else if (disposition === "move" && targetFolder) {
            try {
              await emailApi.batchMove(msgUuids, targetFolder);
            } catch { /* best effort */ }
          }
        }

        // Step 3: Delete the folder
        try {
          await emailApi.deleteFolder(acctEmail, fldName);
        } catch (err) {
          tabStore.open("error", "Delete Failed", {
            message: err.message || `Failed to delete folder: ${path}`,
          });
        }
      }
    } finally {
      deleting = false;
      await refreshList();
      selectedPaths = new Set();
      if (selectionMode && selectedPaths.size === 0) {
        selectionMode = false;
      }
    }
  }

  // Simplified delete (for context menu — uses default "trash" disposition)
  async function handleDeleteFolder(path) {
    promptDelete([path]);
  }

  // Multi-delete from selection mode
  function deleteSelected() {
    if (selectedPaths.size === 0) return;
    promptDelete([...selectedPaths]);
  }

  // ── Context menu ───────────────────────────────────────────────────
  function showContextMenu(path, event) {
    contextMenu = { x: event.clientX, y: event.clientY, path };
  }

  function closeContextMenu() {
    contextMenu = null;
  }

  // ── Drag-to-move ───────────────────────────────────────────────────
  let dragSourcePath = $state("");

  function handleDragStart(path) {
    dragSourcePath = path;
  }

  function _isAncestorOf(ancestor, descendant) {
    if (!ancestor || !descendant) return false;
    return descendant.startsWith(ancestor + "/") || descendant === ancestor;
  }

  async function handleDrop(draggedPath, targetPath) {
    if (!draggedPath || !targetPath || draggedPath === targetPath) return;
    // Prevent cycles: cannot drop parent onto descendant
    if (_isAncestorOf(draggedPath, targetPath)) return;
    // Cannot drop onto itself
    if (draggedPath === targetPath) return;

    // Must have format {account}/{folder}
    const dragSlash = draggedPath.indexOf("/");
    const targetSlash = targetPath.indexOf("/");
    if (dragSlash < 0 || targetSlash < 0) return;

    const dragAcct = draggedPath.slice(0, dragSlash);
    const dragFolder = draggedPath.slice(dragSlash + 1);
    const targetFolder = targetPath.slice(targetSlash + 1);

    try {
      // !email folder move uses --parent {account}/{parent}
      const parentArg = `${dragAcct}/${targetFolder}`;
      // We can use the API to move via command execution, or direct API
      // Direct approach: rename the folder via IMAP RENAME semantics
      await emailApi.renameFolder(dragAcct, dragFolder, `${targetFolder}/${dragFolder.split("/").pop()}`);
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Move Failed", {
        message: err.message || "Failed to move folder",
      });
    }

    dragSourcePath = "";
  }

  // ── Keyboard handler ───────────────────────────────────────────────
  function handleKeydown(e) {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable) return;

    const plain = !e.ctrlKey && !e.metaKey && !e.altKey;

    if (e.key === "Escape") {
      if (contextMenu) { closeContextMenu(); e.preventDefault(); return; }
      if (selectionMode) { toggleSelectionMode(); e.preventDefault(); return; }
      if (showSearch) { showSearch = false; searchQuery = ""; e.preventDefault(); return; }
      if (renaming) { renaming = false; renameError = ""; e.preventDefault(); return; }
      tabStore.close(tabStore.active?.id);
      return;
    }

    if (plain && e.key === "f") { showSearch = !showSearch; e.preventDefault(); return; }
    if (plain && e.key === "n") {
      if (!selectionMode) showNewFolderInput = true;
      e.preventDefault();
      return;
    }
    if (plain && e.key === "v") { toggleSelectionMode(); e.preventDefault(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key === "r") {
      e.preventDefault();
      handleInitialSync();
      return;
    }

    // DELETE key — delete active folder or selected folders
    if (e.key === "Delete" || e.key === "Del" || e.key === "Backspace") {
      if (selectionMode && selectedPaths.size > 0) {
        e.preventDefault();
        deleteSelected();
        return;
      }
      if (!selectionMode && activePath) {
        e.preventDefault();
        promptDelete([activePath]);
        return;
      }
    }

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

  // ── Helpers ────────────────────────────────────────────────────────
  function getFlatFolderList() {
    const result = [];
    function walk(nodes) {
      for (const n of nodes) {
        result.push(n.path);
        if (n.expanded && n.children?.length) walk(n.children);
      }
    }
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

  function handleAccountChange(e) {
    accountFilter = e.target.value;
    refreshList();
  }

  // ── Tree pass-through state ────────────────────────────────────────
  let folderVisibility = $state({});
  let expandedFolders = $state([]);

  function handleToggleFolder(_path) {}
  function handleToggleExpand(path) {
    expandedFolders = expandedFolders.includes(path)
      ? expandedFolders.filter((p) => p !== path)
      : [...expandedFolders, path];
  }

  async function handleTreeCreateFolder(name) {
    if (!accountFilter) throw new Error("Select an account first.");
    await emailApi.createFolder(accountFilter, name);
    await refreshList();
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="folder-tab">
  {#if initialLoading && syncing}
    <SyncOverlay
      {syncProgress}
      title="Syncing folders…"
      {syncError}
      onCancel={stopSync}
    />
  {:else}
    <!-- ── Toolbar ──────────────────────────────────────────────────── -->
    <div class="toolbar">
      <div class="left">
        {#if !selectionMode}
          <!-- View mode -->
          <button class="btn" onclick={() => { showNewFolderInput = true; }} title="Create new folder">
            + New <kbd>N</kbd>
          </button>
          <button class="btn" onclick={toggleSelectionMode} title="Toggle multi-select mode (V)">
            Select <kbd>V</kbd>
          </button>
          <button class="btn" onclick={() => { handleInitialSync(); }} disabled={syncing} title="Sync (Ctrl+R)">
            {syncing ? "⟳ Syncing…" : "⟳ Sync <kbd>Ctrl+R</kbd>"}
          </button>
          <button class="btn" onclick={() => { showSearch = !showSearch; }} title="Search folders (F)">
            🔍 Search <kbd>F</kbd>
          </button>
        {:else}
          <!-- Selection mode -->
          <button class="btn" onclick={toggleSelectionMode} title="Exit selection mode (V)">
            Done <kbd>V</kbd>
          </button>
          <span class="selected-count">{numSelected} selected</span>
          {#if numSelected > 0}
            <button class="btn danger" onclick={deleteSelected} title="Delete selected folders (Delete)">
              Delete <kbd>Del</kbd>
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

    <!-- ── Search bar ──────────────────────────────────────────────── -->
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

    <!-- ── Sync error banner ───────────────────────────────────────── -->
    {#if syncError && !initialLoading}
      <div class="sync-error" role="alert">{syncError}</div>
    {/if}

    <!-- ── Inline new-folder form ──────────────────────────────────── -->
    {#if showNewFolderInput}
      <div class="inline-form">
        <input
          type="text"
          class="form-input"
          placeholder={activePath ? `Subfolder of ${activePath.split("/").pop()}` : "New folder name (at root)"}
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

    <!-- ── Rename inline form ──────────────────────────────────────── -->
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

    <!-- ── Folder tree ─────────────────────────────────────────────── -->
    <div class="tree-wrapper">
      <EmailFolderTree
        folders={filteredFolders}
        bind:folderVisibility
        bind:expandedFolders
        onToggleFolder={handleToggleFolder}
        onToggleExpand={handleToggleExpand}
        onCreateFolder={handleTreeCreateFolder}
        showCheckboxes={selectionMode}
        {activePath}
        onActivate={handleActivate}
        onContextMenu={showContextMenu}
        onDoubleClick={handleStartRename}
        onDragStart={handleDragStart}
        onDrop={handleDrop}
      />
    </div>

    <!-- ── Empty state ─────────────────────────────────────────────── -->
    {#if filteredFolders.length === 0}
      <p class="empty">
        {#if accountFilter}
          No folders found for {accountFilter}.
        {:else}
          No folders found. Use <strong>!email folder add --parent</strong> to create one.
        {/if}
      </p>
    {/if}
  {/if}
</div>

<!-- ── Context menu ──────────────────────────────────────────────── -->
{#if contextMenu}
  <FolderContextMenu
    x={contextMenu.x}
    y={contextMenu.y}
    folderPath={contextMenu.path}
    onRename={handleStartRename}
    onDelete={handleDeleteFolder}
    onClose={closeContextMenu}
  />
{/if}

<!-- ── Delete confirmation dialog ────────────────────────────────── -->
{#if confirmDelete}
  <FolderDeleteDialog
    folderPaths={pendingDeletePaths}
    onDelete={handleDeleteWithDisposition}
    onDismiss={() => { confirmDelete = false; pendingDeletePaths = []; }}
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

  .btn kbd {
    display: inline-block;
    padding: 0 2px;
    margin-left: 1px;
    font-family: monospace;
    font-size: 0.68rem;
    background: #222;
    border: 1px solid #555;
    border-radius: 2px;
    color: #999;
    line-height: 1.3;
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

  .sync-error {
    padding: 0.3rem 0.5rem;
    background: #3a1a1a;
    border-bottom: 1px solid #6a2a2a;
    color: #e8a0a0;
    font-size: 0.78rem;
  }

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
