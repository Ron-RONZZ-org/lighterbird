<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi } from "./api.js";
  import EmailListToolbar from "./EmailListToolbar.svelte";
  import EmailFolderTree from "./EmailFolderTree.svelte";
  import EmailListRow from "./EmailListRow.svelte";
  import EmailParamsDialog from "./EmailParamsDialog.svelte";
  import SortDropdown from "./SortDropdown.svelte";
  import MoveDialog from "./MoveDialog.svelte";
  import KeyboardShortcutOverlay from "./KeyboardShortcutOverlay.svelte";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import ExportDialog from "./ExportDialog.svelte";
  import ImportDialog from "./ImportDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
  } from "./listTabShared.svelte.js";
  import { createEmailConfigStore } from "./emailConfigStore.svelte.js";
  import { registerShortcuts } from "./keyboardShortcuts.svelte.js";

  registerShortcuts("EmailListTab", [
    { key: "f", desc: "Toggle folder tree", category: "Email List" },
    { key: "s", desc: "Change sort order", category: "Email List" },
    { key: "p", desc: "Toggle params dialog", category: "Email List" },
    { key: "r", desc: "Reply to selected message", category: "Email List" },
    { key: "Ctrl+R", desc: "Sync emails", modifiers: "Ctrl", category: "Email List" },
    { key: "Ctrl+M", desc: "Move selected messages", modifiers: "Ctrl", category: "Email List" },
  ]);

  let { data = {} } = $props();
  let messages = $derived(data?.messages || []);
  let total = $derived(data?.total || 0);
  let syncing = $state(false);

  // ── Config store ─────────────────────────────────────────────────────
  let config = $state(createEmailConfigStore());
  let folderVisibility = $state({});
  let expandedFolders = $state([]);
  let sort = $state("newest");
  let groupByConversation = $state(false);
  let groupBySender = $state(false);

  // Sync config when tab data changes (e.g., !email list --sort oldest)
  // and re-query the backend so the sort/group/folder params take effect.
  $effect(() => {
    if (data?.filters) {
      const cliFlags = {};
      if (data.filters.folder) cliFlags.folder = data.filters.folder;
      if (data.filters.sort) cliFlags.sort = data.filters.sort;
      if (data.filters.group === "conversation") cliFlags.group = "conversation";
      if (data.filters.group === "sender") cliFlags.group = "sender";
      let needsRequery = false;
      if (Object.keys(cliFlags).length > 0) {
        // CLI flags from the backend command are already applied — just apply
        // matching config so the toolbar reflects the correct state.
        const merged = config.mergeWithCliFlags(cliFlags);
        folderVisibility = merged.folderVisibility || {};
        sort = merged.sort || "newest";
        groupByConversation = !!merged.groupByConversation;
        groupBySender = !!merged.groupBySender;
        // No re-query needed — CLI response is the authoritative view
        needsRequery = false;
      } else {
        // No CLI flags — apply lastConfig from store
        const lastCfg = config.getLastConfig();
        folderVisibility = lastCfg.folderVisibility || {};
        expandedFolders = lastCfg.expandedFolders || [];
        sort = lastCfg.sort || "newest";
        groupByConversation = !!lastCfg.groupByConversation;
        groupBySender = !!lastCfg.groupBySender;
        // When restoring from lastConfig, only re-query if sort differs from default
        needsRequery = lastCfg.sort !== "newest" || !!lastCfg.groupByConversation || !!lastCfg.groupBySender;
      }
      if (needsRequery) {
        applyFolderFilter();
      }
    }
  });

  // Folders for the tree
  let folders = $state([]);
  $effect(() => {
    emailApi.listFolders().then((res) => {
      folders = res.folders || [];
    }).catch(() => {});
  });

  // Shared copy states
  let uuidCopy = createCopyState();
  let emailCopy = createCopyState();

  // Shared selection state
  let sel = createSelectionManager(
    () => messages,
    (uuid) => openMessage(uuid),
    async (uuids) => {
      await emailApi.batchDelete(uuids);
    },
    () => refreshList(),
    {
      onNew: handleNew,
      onBeforeKeydown(e) {
        const tag = e.target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) return true;

        if (showMoveDialog) {
          if (e.key === "Escape") { showMoveDialog = false; e.preventDefault(); }
          return true;
        }

        const plain = !e.ctrlKey && !e.metaKey && !e.altKey;
        switch (e.key) {
          case "e":
            if (plain && sel.selectionMode && sel.numSelected > 0) {
              openExportDialog(); e.preventDefault();
            }
            return true;
          case "/":
            if (plain) {
              showSearch = !showSearch;
              if (showSearch) requestAnimationFrame(() => document.querySelector(".search-input")?.focus());
              else closeSearch();
              e.preventDefault();
            }
            return true;
          case "f":
          case "F":
            if (plain) { showFolderTree = !showFolderTree; e.preventDefault(); }
            return true;
          case "s":
          case "S":
            if (plain) { showSortDropdown = !showSortDropdown; e.preventDefault(); }
            return true;
          case "p":
          case "P":
            if (plain) { showParamsDialog = !showParamsDialog; e.preventDefault(); }
            return true;
          case "Escape":
            if (showShortcutHelp) { showShortcutHelp = false; e.preventDefault(); return true; }
            if (showSearch) { closeSearch(); e.preventDefault(); return true; }
            if (showMoveDialog) { showMoveDialog = false; e.preventDefault(); return true; }
            if (showFolderTree) { showFolderTree = false; e.preventDefault(); return true; }
            if (showSortDropdown) { showSortDropdown = false; e.preventDefault(); return true; }
            if (showParamsDialog) { showParamsDialog = false; e.preventDefault(); return true; }
            if (sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); return true; }
            // No active UI state — close the tab
            tabStore.close(tabStore.active?.id);
            return true;
        }

        if ((e.ctrlKey || e.metaKey) && e.key === "r") {
          e.preventDefault();
          handleSync();
          return true;
        }

        if ((e.ctrlKey || e.metaKey) && e.key === "m") {
          e.preventDefault();
          if (sel.numSelected > 0) showMoveDialog = true;
          return true;
        }

        return false;
      },
    }
  );

  let showMoveDialog = $state(false);
  let showShortcutHelp = $state(false);
  let showFolderTree = $state(false);
  let showSortDropdown = $state(false);
  let showParamsDialog = $state(false);
  let showImportDialog = $state(false);
  let showExportDialog = $state(false);

  let exportItems = $derived(messages.filter(m => sel.selectedKeys.has(m.uuid)));

  function openImportDialog() {
    showImportDialog = true;
  }

  function openExportDialog() {
    showExportDialog = true;
  }

  function handleNew() {
    tabStore.open("form", "Compose Email", { form: "email-send", initialData: { _returnIdKey: "persistent-email-list" } }, {
      idKey: "email-compose",
    });
  }

  $effect(() => {
    function handler() { showShortcutHelp = !showShortcutHelp; }
    window.addEventListener("help-toggle", handler);
    return () => window.removeEventListener("help-toggle", handler);
  });

  let showSearch = $state(false);
  let searchQuery = $state("");
  let currentFilters = $state({});
  let searchTimeout;
  let abortController = null;

  function handleRowClick(e, msg) {
    if (sel.selectionMode) {
      sel.handleRowClick(e, msg.uuid);
    } else if (e.ctrlKey || e.metaKey || e.button === 1) {
      openMessageInNewTab(e, msg.uuid);
    } else {
      openMessage(msg.uuid);
    }
  }

  async function openMessage(uuid) {
    if (!uuid) return;
    try {
      const msg = await emailApi.getMessage(uuid);
      tabStore.open("email", msg.subject || "(no subject)", msg, {
        idKey: `email-${uuid}`,
        replaceable: false,
      });
    } catch (err) {
      tabStore.open("error", "Error", { message: err.message || "Failed to load message" });
    }
  }

  function openMessageInNewTab(e, uuid) {
    if (!uuid) return;
    e.preventDefault();
    window.open(`/api/v1/email/messages/${uuid}/view`, "_blank");
  }

  async function deleteSelected() {
    const uuids = [...sel.selectedKeys];
    if (uuids.length === 0) return;
    try {
      await emailApi.batchDelete(uuids);
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Delete Failed", {
        message: err.message || "Failed to delete messages",
      });
    }
  }

  async function handleMoveConfirmed(destinationFolderUuid) {
    const uuids = [...sel.selectedKeys];
    if (uuids.length === 0) return;
    try {
      await emailApi.batchMove(uuids, destinationFolderUuid);
      showMoveDialog = false;
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Move Failed", {
        message: err.message || "Failed to move messages",
      });
    }
  }

  $effect(() => {
    if (data && (data.filters !== undefined || data.query !== undefined)) {
      const newFilters = data.filters || {};
      // Avoid unnecessary object reference change that triggers cascading effects
      if (JSON.stringify(currentFilters) !== JSON.stringify(newFilters)) {
        currentFilters = newFilters;
      }
      searchQuery = data.query || "";
      showSearch = !!(data.query);
    }
  });

  function performSearch(query) {
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const params = { ...currentFilters, limit: 50 };
    if (query && query.length >= 2) {
      params.query = query;
    }
    emailApi.listMessages(params)
      .then((result) => {
        tabStore.update(tabStore.active.id, result);
      })
      .catch((err) => {
        if (err?.name === "AbortError") return;
      });
  }

  function handleSearchInput(e) {
    const val = e.target.value;
    searchQuery = val;
    clearTimeout(searchTimeout);
    if (val.length === 0 || val.length >= 2) {
      searchTimeout = setTimeout(() => performSearch(val), 300);
    }
  }

  function closeSearch() {
    showSearch = false;
    searchQuery = "";
    if (data?.query) performSearch("");
    document.querySelector(".email-list .list")?.focus();
  }

  async function refreshList() {
    try {
      const params = { ...currentFilters, limit: 50 };
      if (searchQuery && searchQuery.length >= 2) {
        params.query = searchQuery;
      }
      const result = await emailApi.listMessages(params);
      tabStore.update(tabStore.active.id, result);
    } catch { /* silent */ }
  }

  async function handleSync() {
    if (syncing) return;
    syncing = true;
    try {
      await emailApi.sync();
      await refreshList();
    } catch { /* silent */ }
    finally { syncing = false; }
  }

  // Live-update read status — handled in App.svelte (always-mounted root)

  // ── Folder tree callbacks ──────────────────────────────────────────
  function handleToggleFolder(folderName) {
    const next = { ...folderVisibility };
    next[folderName] = !(next[folderName] !== false);
    folderVisibility = next;
    config.autoSave({ folderVisibility: next });
    // Refresh list with the new folder filter
    applyFolderFilter();
  }

  function handleToggleExpand(path) {
    const next = expandedFolders.includes(path)
      ? expandedFolders.filter((p) => p !== path)
      : [...expandedFolders, path];
    expandedFolders = next;
    config.autoSave({ expandedFolders: next });
  }

  function handleSortChange(val) {
    sort = val;
    config.autoSave({ sort: val, groupBySender: false });
    if (groupBySender) { groupBySender = false; }
    applyFolderFilter();
  }

  function handleGroupChange(val) {
    groupByConversation = val;
    config.autoSave({ groupByConversation: val });
    applyFolderFilter();
  }

  function handleGroupBySenderChange(val) {
    groupBySender = val;
    config.autoSave({ groupBySender: val });
    applyFolderFilter();
  }

  async function handleCreateFolder(folderName) {
    // Determine the account from the first folder in the list
    const firstFolder = folders[0];
    if (!firstFolder || !firstFolder.account_email) {
      throw new Error("No email account found. Configure an account first.");
    }
    await emailApi.createFolder(firstFolder.account_email, folderName);
    // Auto-sync: re-fetch folder list
    const res = await emailApi.listFolders();
    folders = res.folders || [];
  }

  function applyFolderFilter() {
    // Determine which folders to show
    const visibleFolders = Object.entries(folderVisibility)
      .filter(([_, visible]) => visible)
      .map(([name]) => {
        // Extract folder name from "account/folder_name" format
        const parts = name.split("/");
        return parts.length > 1 ? parts.slice(1).join("/") : name;
      });

    const params = { ...currentFilters, limit: 50 };
    if (visibleFolders.length > 0) {
      params.folder = visibleFolders.join(",");
    }
    if (sort) params.sort = sort;
    if (groupByConversation) params.group = "conversation";
    if (groupBySender) params.group = "sender";
    if (searchQuery && searchQuery.length >= 2) {
      params.query = searchQuery;
    }
    emailApi.listMessages(params)
      .then((result) => {
        tabStore.update(tabStore.active.id, result);
      })
      .catch(() => {});
  }

  // ── Config dialog callbacks ────────────────────────────────────────
  function handleSaveConfig(name) {
    config.saveAs(name);
  }

  function handleActivateConfig(name) {
    config.activate(name);
    const cfg = config.getLastConfig();
    folderVisibility = cfg.folderVisibility || {};
    expandedFolders = cfg.expandedFolders || [];
    sort = cfg.sort || "newest";
    groupByConversation = !!cfg.groupByConversation;
    applyFolderFilter();
  }

  function handleDeleteConfig(name) {
    config.remove(name);
  }

  function handleWindowKeydown(e) {
    sel.handleKeydown(e);
  }

  // Save config on tab close
  $effect(() => {
    // Flush on unmount
    return () => { config.flush(); };
  });
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="email-list">
  <!-- Toolbar -->
  <EmailListToolbar
    selectionMode={sel.selectionMode}
    numSelected={sel.numSelected}
    {showSearch}
    {searchQuery}
    {showFolderTree}
    onToggleMode={() => sel.toggleSelectionMode()}
    onDelete={() => { if (sel.numSelected > 0) sel.confirmDelete = true; }}
    onMove={() => { if (sel.numSelected > 0) showMoveDialog = true; }}
    onNew={handleNew}
    onToggleSearch={() => { showSearch = !showSearch; if (showSearch) requestAnimationFrame(() => document.querySelector(".search-input")?.focus()); }}
    onSearchInput={handleSearchInput}
    onSearchClear={() => { searchQuery = ""; performSearch(""); }}
    onSearchEscape={closeSearch}
    onSearchEnter={() => performSearch(searchQuery)}
    onToggleFolderTree={() => { showFolderTree = !showFolderTree; }}
    onToggleSortDropdown={() => { showSortDropdown = !showSortDropdown; }}
    onToggleParamsDialog={() => { showParamsDialog = !showParamsDialog; }}
    onImport={openImportDialog}
    onExport={openExportDialog}
    onSync={handleSync}
    {syncing}
  />

  <!-- Folder tree dropdown overlay -->
  {#if showFolderTree}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="dropdown-backdrop" onclick={() => { showFolderTree = false; }} role="presentation"></div>
    <div class="dropdown-panel folder-panel">
      <EmailFolderTree
        {folders}
        {folderVisibility}
        {expandedFolders}
        {sort}
        {groupByConversation}
        {groupBySender}
        onToggleFolder={handleToggleFolder}
        onToggleExpand={handleToggleExpand}
        onSortChange={handleSortChange}
        onGroupChange={handleGroupChange}
        onGroupBySenderChange={handleGroupBySenderChange}
        onCreateFolder={handleCreateFolder}
      />
    </div>
  {/if}

  <!-- Sort dropdown overlay -->
  {#if showSortDropdown}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="dropdown-backdrop" onclick={() => { showSortDropdown = false; }} role="presentation"></div>
    <div class="dropdown-panel sort-panel">
      <SortDropdown
        {sort}
        {groupByConversation}
        {groupBySender}
        onSortChange={handleSortChange}
        onGroupChange={handleGroupChange}
        onGroupBySenderChange={handleGroupBySenderChange}
      />
    </div>
  {/if}

  <!-- Params dialog -->
  {#if showParamsDialog}
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="dropdown-backdrop" onclick={() => { showParamsDialog = false; }} role="presentation"></div>
    <div class="dropdown-panel">
      <EmailParamsDialog
        {config}
        onSave={handleSaveConfig}
        onActivate={handleActivateConfig}
        onDelete={handleDeleteConfig}
        onClose={() => { showParamsDialog = false; }}
      />
    </div>
  {/if}

  <!-- Message list -->
  <div class="list" role="listbox" aria-label="Email messages" aria-multiselectable="true">
    {#each messages as msg, i (msg.uuid)}
      <EmailListRow
        {msg}
        index={i}
        isSelected={sel.isSelected(msg.uuid)}
        isFocused={i === sel.focusedIndex}
        selectionMode={sel.selectionMode}
        {uuidCopy}
        {emailCopy}
        onRowClick={handleRowClick}
      />
    {:else}
      <p class="empty">No messages.</p>
    {/each}
  </div>

  {#if sel.confirmDelete}
    <ConfirmDialog
      message="Delete {sel.numSelected} message{sel.numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { sel.confirmDelete = false; await deleteSelected(); }}
      onDismiss={() => { sel.confirmDelete = false; }}
    />
  {/if}

  {#if showMoveDialog}
    <MoveDialog
      onConfirm={(destUuid) => handleMoveConfirmed(destUuid)}
      onDismiss={() => { showMoveDialog = false; }}
    />
  {/if}

  {#if showShortcutHelp}
    <KeyboardShortcutOverlay onDismiss={() => { showShortcutHelp = false; }} />
  {/if}

  {#if showExportDialog}
    <ExportDialog
      domain="email"
      items={exportItems}
      format="eml"
      onClose={() => showExportDialog = false}
    />
  {/if}
  {#if showImportDialog}
    <ImportDialog
      domain="email"
      format="eml"
      onClose={() => showImportDialog = false}
    />
  {/if}
</div>

<style>
  .email-list {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-family: monospace;
    font-size: 0.85rem;
    position: relative;
  }

  .list {
    flex: 1;
    overflow-y: auto;
    padding: 0;
  }

  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }

  /* Dropdown overlay */
  .dropdown-backdrop {
    position: fixed;
    inset: 0;
    z-index: 200;
    background: transparent;
  }
  .dropdown-panel {
    position: absolute;
    top: 2.4rem;
    left: 0.3rem;
    z-index: 300;
    background: #1e1e32;
    border: 1px solid #4a4a6a;
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    max-height: 70vh;
    overflow-y: auto;
  }
  .folder-panel {
    width: 320px;
    padding: 0.75rem;
  }
</style>
