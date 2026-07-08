<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi } from "./api.js";
  import { openMessage, openMessageInNewTab, handleRowClick, deleteSelected, moveSelected } from "./emailMessageOps.svelte.js";
  import EmailListToolbar from "./EmailListToolbar.svelte";
  import EmailFolderPanel from "./EmailFolderPanel.svelte";
  import AdvancedSearchDialog from "./AdvancedSearchDialog.svelte";
  import SearchTileBar from "./SearchTileBar.svelte";
  import EmailListRow from "./EmailListRow.svelte";
  import EmailParamsDialog from "./EmailParamsDialog.svelte";
  import EmailSortOverlay from "./EmailSortOverlay.svelte";
  import DropdownPanel from "./DropdownPanel.svelte";
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
    { key: "l", desc: "Load more messages", category: "Email List" },
    { key: "Ctrl+R", desc: "Sync emails", modifiers: "Ctrl", category: "Email List" },
    { key: "Ctrl+M", desc: "Move selected messages", modifiers: "Ctrl", category: "Email List" },
  ]);

  let { data = {} } = $props();
  let messages = $state([]);
  let total = $derived(messages.length);
  let hasMore = $state(false);
  let nextCursor = $state("");
  let loadingMore = $state(false);
  let syncing = $state(false);

  // When data prop changes (new query / new tab data), reset pagination
  $effect(() => {
    if (data?.messages) {
      messages = data.messages;
      hasMore = !!data.has_more;
      nextCursor = data.next_cursor || "";
    }
  });

  // ── Config store ─────────────────────────────────────────────────────
  let config = $state(createEmailConfigStore());
  let folderVisibility = $state({});
  let expandedFolders = $state([]);
  let sort = $state("newest");
  let groupByConversation = $state(false);
  let groupBySender = $state(false);

  $effect(() => {
    if (!data?.filters) return;
    const cliFlags = {};
    if (data.filters.folder) cliFlags.folder = data.filters.folder;
    if (data.filters.sort) cliFlags.sort = data.filters.sort;
    if (data.filters.group === "conversation") cliFlags.group = "conversation";
    if (data.filters.group === "sender") cliFlags.group = "sender";
    if (Object.keys(cliFlags).length > 0) {
      const merged = config.mergeWithCliFlags(cliFlags);
      folderVisibility = merged.folderVisibility || {};
      sort = merged.sort || "newest";
      groupByConversation = !!merged.groupByConversation;
      groupBySender = !!merged.groupBySender;
    } else {
      const lastCfg = config.getLastConfig();
      folderVisibility = lastCfg.folderVisibility || {};
      expandedFolders = lastCfg.expandedFolders || [];
      sort = lastCfg.sort || "newest";
      groupByConversation = !!lastCfg.groupByConversation;
      groupBySender = !!lastCfg.groupBySender;
      const needsRequery = lastCfg.sort !== "newest" || !!lastCfg.groupByConversation || !!lastCfg.groupBySender;
      if (needsRequery) applyFolderFilter();
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
        if (showMoveDialog && e.key === "Escape") { showMoveDialog = false; e.preventDefault(); return true; }
        const plain = !e.ctrlKey && !e.metaKey && !e.altKey;
        switch (e.key) {
          case "e": if (plain && sel.selectionMode && sel.numSelected > 0) { openExportDialog(); e.preventDefault(); } return true;
          case "/": if (plain) { showSearch = !showSearch; if (showSearch) requestAnimationFrame(() => document.querySelector(".search-input")?.focus()); else closeSearch(); e.preventDefault(); } return true;
          case "f": case "F": if (plain) { showFolderTree = !showFolderTree; e.preventDefault(); } return true;
          case "s": case "S": if (plain) { showSortDropdown = !showSortDropdown; e.preventDefault(); } return true;
          case "p": case "P": if (plain) { showParamsDialog = !showParamsDialog; e.preventDefault(); } return true;
          case "l": case "L": if (plain && hasMore) { loadMore(); e.preventDefault(); } return true;
          case "Escape":
            if (showShortcutHelp) { showShortcutHelp = false; e.preventDefault(); return true; }
            if (showSearch) { closeSearch(); e.preventDefault(); return true; }
            if (showMoveDialog) { showMoveDialog = false; e.preventDefault(); return true; }
            if (showFolderTree) { showFolderTree = false; e.preventDefault(); return true; }
            if (showSortDropdown) { showSortDropdown = false; e.preventDefault(); return true; }
            if (showParamsDialog) { showParamsDialog = false; e.preventDefault(); return true; }
            if (sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); return true; }
            tabStore.close(tabStore.active?.id); return true;
        }
        if ((e.ctrlKey || e.metaKey) && e.key === "r") { e.preventDefault(); handleSync(); return true; }
        if ((e.ctrlKey || e.metaKey) && e.key === "m") { e.preventDefault(); if (sel.numSelected > 0) showMoveDialog = true; return true; }
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
  let showAdvancedSearch = $state(false);
  let advancedSearchFilters = $state({});
  let searchKey = $state(0); // increment to trigger re-search

  let exportItems = $derived(messages.filter(m => sel.selectedKeys.has(m.uuid)));

  function openImportDialog() {
    showImportDialog = true;
  }

  function openExportDialog() {
    showExportDialog = true;
  }

  function handleAdvancedSearch(filters) {
    advancedSearchFilters = filters;
    searchKey++;
    performSearch(searchQuery, filters);
  }

  function handleRemoveFilter(key) {
    const next = { ...advancedSearchFilters };
    delete next[key];
    advancedSearchFilters = next;
    searchKey++;
    performSearch(searchQuery, next);
  }

  function handleClearFilters() {
    advancedSearchFilters = {};
    searchKey++;
    performSearch(searchQuery, {});
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

  // handleRowClick, openMessage, openMessageInNewTab, deleteSelected
  // and moveSelected are imported from emailMessageOps.svelte.js

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

  function performSearch(query, extraFilters) {
    const tabId = tabStore.active.id;
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const params = { ...currentFilters, ...(extraFilters || {}), limit: 50 };
    if (query && query.length >= 2) {
      params.query = query;
    }
    emailApi.listMessages(params)
      .then((result) => {
        tabStore.safeUpdate(tabId, result);
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
    const tabId = tabStore.active.id;
    try {
      const params = { ...currentFilters, limit: 50 };
      if (searchQuery && searchQuery.length >= 2) {
        params.query = searchQuery;
      }
      const result = await emailApi.listMessages(params);
      tabStore.safeUpdate(tabId, result);
    } catch { /* silent */ }
  }

  async function loadMore() {
    if (!nextCursor || loadingMore) return;
    loadingMore = true;
    try {
      const params = { ...currentFilters, limit: 50, cursor: nextCursor };
      const result = await emailApi.listMessages(params);
      messages = [...messages, ...(result.messages || [])];
      hasMore = !!result.has_more;
      nextCursor = result.next_cursor || "";
    } catch { /* silent */ }
    finally { loadingMore = false; }
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

  // ── Auto-save config when folder/sort/group state changes ──────────
  $effect(() => {
    config.autoSave({ folderVisibility, expandedFolders, sort, groupByConversation, groupBySender });
  });

  // ── Folder tree callbacks ──────────────────────────────────────────
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
    const tabId = tabStore.active.id;
    emailApi.listMessages(params)
      .then((result) => {
        tabStore.safeUpdate(tabId, result);
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
    onToggleMode={() => {
      // If search is active, close it first so the selection toolbar is shown
      if (showSearch) closeSearch();
      sel.toggleSelectionMode();
    }}
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
    onToggleAdvancedSearch={() => showAdvancedSearch = true}
    {syncing}
  />

  <!-- Advanced search button -->
  <div class="adv-search-row">
    <button class="adv-search-btn" onclick={() => showAdvancedSearch = true}
            title="Advanced search (all fields)">
      <span class="adv-icon">[a]</span> Advanced
    </button>
  </div>

  <!-- Folder tree panel -->
  <EmailFolderPanel
    folderTree={folders}
    bind:folderVisibility
    bind:expandedFolders
    bind:show={showFolderTree}
    onRefresh={applyFolderFilter}
    onCreateFolder={handleCreateFolder}
    onClose={() => { showFolderTree = false; }}
  />

  <!-- Advanced search tile bar -->
  <SearchTileBar
    filters={advancedSearchFilters}
    onRemove={handleRemoveFilter}
    onClear={handleClearFilters}
  />

  <!-- Sort dropdown overlay -->
  <EmailSortOverlay
    bind:sort
    bind:groupByConversation
    bind:groupBySender
    bind:show={showSortDropdown}
    onRefresh={applyFolderFilter}
    onClose={() => { showSortDropdown = false; }}
  />

  <!-- Params dialog -->
  <DropdownPanel show={showParamsDialog} onClose={() => { showParamsDialog = false; }}>
    <EmailParamsDialog
      {config}
      onSave={handleSaveConfig}
      onActivate={handleActivateConfig}
      onDelete={handleDeleteConfig}
      onClose={() => { showParamsDialog = false; }}
    />
  </DropdownPanel>

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
        onRowClick={(e, msg) => handleRowClick(e, msg, sel)}
      />
    {:else}
      <p class="empty">No messages.</p>
    {/each}
    {#if hasMore}
      <button class="load-more" onclick={loadMore} disabled={loadingMore}>
        {loadingMore ? "Loading…" : "Load more"}
      </button>
    {/if}
  </div>

  {#if sel.confirmDelete}
    <ConfirmDialog
      message="Delete {sel.numSelected} message{sel.numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { await sel.deleteSelected(); sel.confirmDelete = false; }}
      onDismiss={() => { sel.confirmDelete = false; }}
    />
  {/if}

  {#if showMoveDialog}
    <MoveDialog
      onConfirm={async (destUuid) => { await moveSelected([...sel.selectedKeys], destUuid, refreshList); showMoveDialog = false; }}
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
  {#if showAdvancedSearch}
    <AdvancedSearchDialog
      show={showAdvancedSearch}
      currentFilters={advancedSearchFilters}
      onSearch={handleAdvancedSearch}
      onClose={() => showAdvancedSearch = false}
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

  .load-more {
    display: block;
    width: 100%;
    padding: 0.6rem;
    text-align: center;
    background: var(--clr-surface, #2a2a3e);
    border: 1px solid var(--clr-border, #4a4a6a);
    border-radius: 0 0 4px 4px;
    color: var(--clr-primary, #7c9bff);
    cursor: pointer;
    font: inherit;
    transition: background 0.15s;
  }
  .load-more:hover:not(:disabled) {
    background: var(--clr-hover, #3a3a52);
  }
  .load-more:disabled {
    color: var(--clr-muted, #888);
    cursor: default;
  }

  .adv-search-row {
    display: flex;
    align-items: center;
    padding: 0.25rem 0.75rem;
    gap: 0.5rem;
    border-bottom: 1px solid #2a2a3e;
    background: #1a1a2e;
  }
  .adv-search-btn {
    background: transparent;
    border: 1px solid #4a4a6a;
    border-radius: 4px;
    color: #7c9bff;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.78rem;
    padding: 0.2rem 0.5rem;
    transition: background 0.1s, border-color 0.1s;
  }
  .adv-search-btn:hover {
    background: #2a2a4e;
    border-color: #6a6a9a;
  }
  .adv-icon {
    color: #7fdb7f;
    font-weight: bold;
  }

</style>
