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
  import ProgressBar from "./ProgressBar.svelte";
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
    { key: "a", desc: "Open advanced search", category: "Email List" },
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
  let syncTaskId = $state(null);
  let syncProgress = $state(null);
  let syncPollTimer = $state(null);
  let syncError = $state("");

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
          case "a": case "A": if (plain) { showAdvancedSearch = true; e.preventDefault(); } return true;
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

  /**
   * Translate local filter format to API params.
   * - header_text → query + header=true  (local SQL on headers)
   * - body_text   → query + body=true    (IMAP SEARCH)
   * - date_from   → after (API)
   * - date_to     → before (API)
   */
  function filtersToApiParams(filters) {
    const params = {};
    if (filters.header_text) params.query = filters.header_text;
    if (filters.body_text) params.query = filters.body_text;
    if (filters.from) params.from = filters.from;
    if (filters.subject) params.subject = filters.subject;
    if (filters.to) params.to = filters.to;
    if (filters.cc) params.cc = filters.cc;
    if (filters.bcc) params.bcc = filters.bcc;
    if (filters.participant) params.participant = filters.participant;
    if (filters.priority) params.priority = filters.priority;
    if (filters.folder) params.folder = filters.folder;
    if (filters.date_from) params.after = filters.date_from;
    if (filters.date_to) params.before = filters.date_to;
    if (filters.header_text) params.header = "true";
    if (filters.body_text) params.body = "true";
    return params;
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
    const tabId = tabStore.findByKey("persistent-email-list") || tabStore.active.id;
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const signal = abortController.signal;

    // Build params: start with advanced filters, then add search bar query
    const params = { ...currentFilters, ...filtersToApiParams(extraFilters || {}), limit: 50 };

    // Free-text from the search bar (/) — default: all fields
    if (query && query.length >= 2) {
      // Two-phase search:
      // Phase 1: headers only (fast, local SQL) → show results immediately
      // Phase 2: body search (IMAP SEARCH, slower) → append additional results
      const headerParams = { ...params, query, header: "true", limit: 50 };
      emailApi.listMessages(headerParams, signal)
        .then((result) => {
          if (signal.aborted) return;
          tabStore.safeUpdate(tabId, result);
          // Phase 2: body search
          const bodyParams = { ...params, query, body: "true", limit: 50 };
          emailApi.listMessages(bodyParams, signal)
            .then((bodyResult) => {
              if (signal.aborted) return;
              const merged = mergeSearchResults(result, bodyResult);
              tabStore.safeUpdate(tabId, merged);
            })
            .catch((err) => {
              if (err?.name === "AbortError") return;
            });
        })
        .catch((err) => {
          if (err?.name === "AbortError") return;
        });
    } else {
      // No free-text query: just send filters (advanced search case)
      if (params.header_text || params.body_text || Object.keys(params).length > 1) {
        emailApi.listMessages(params, signal)
          .then((result) => {
            if (signal.aborted) return;
            tabStore.safeUpdate(tabId, result);
          })
          .catch((err) => {
            if (err?.name === "AbortError") return;
          });
      }
    }
  }

  /**
   * Merge two search results, deduplicating by uuid.
   * Header results come first, then body-only results appended.
   */
  function mergeSearchResults(headerResult, bodyResult) {
    const seen = new Set();
    const merged = [];
    for (const msg of (headerResult.messages || [])) {
      seen.add(msg.uuid);
      merged.push(msg);
    }
    for (const msg of (bodyResult.messages || [])) {
      if (!seen.has(msg.uuid)) {
        seen.add(msg.uuid);
        merged.push(msg);
      }
    }
    return {
      messages: merged,
      total: merged.length,
      has_more: headerResult.has_more || bodyResult.has_more,
      next_cursor: headerResult.next_cursor || bodyResult.next_cursor,
    };
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
    // Resolve the email list tab by its persistent idKey so the update
    // lands on the correct tab even if the user switched away during an
    // async operation (sync, search, pagination).  Fall back to the
    // currently active tab for non-list callers (delete, move).
    const tabId = tabStore.findByKey("persistent-email-list") || tabStore.active.id;
    try {
      const params = { ...currentFilters, limit: 50 };
      if (searchQuery && searchQuery.length >= 2) {
        params.query = searchQuery;
      }
      const [result, folderResult] = await Promise.all([
        emailApi.listMessages(params),
        emailApi.listFolders(),
      ]);
      tabStore.safeUpdate(tabId, result);
      folders = folderResult.folders || [];
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
    syncProgress = null;
    syncTaskId = null;
    syncError = "";

    try {
      const startResult = await emailApi.syncStart();
      syncTaskId = startResult.task_id;
      pollSyncProgress();
    } catch (err) {
      syncError = `Sync failed to start: ${err?.message || err || "Unknown error"}`;
      syncing = false;
      clearSyncError();
    }
  }

  function syncErrorMsg(errors) {
    if (!errors || errors.length === 0) return "";
    return errors.join("; ");
  }

  function clearSyncError() {
    setTimeout(() => { syncError = ""; }, 8000);
  }

  function pollSyncProgress() {
    if (!syncTaskId) return;
    const poll = async () => {
      try {
        const prog = await emailApi.getSyncProgress(syncTaskId);
        if (!prog) { stopSync(); return; }
        syncProgress = prog;
        if (prog.status === "complete") {
          syncProgress = prog;
          syncing = false;
          syncTaskId = null;
          if (prog.errors && prog.errors.length > 0) {
            syncError = `Sync completed with errors: ${syncErrorMsg(prog.errors)}`;
            clearSyncError();
          }
          await refreshList();
        } else if (prog.status === "error") {
          syncProgress = prog;
          syncing = false;
          syncTaskId = null;
          syncError = `Sync failed: ${syncErrorMsg(prog.errors) || "Unknown error"}`;
          clearSyncError();
        } else {
          syncPollTimer = setTimeout(poll, 1500);
        }
      } catch {
        stopSync();
      }
    };
    syncPollTimer = setTimeout(poll, 500);
  }

  function stopSync() {
    syncing = false;
    syncTaskId = null;
    syncProgress = null;
    if (syncPollTimer) { clearTimeout(syncPollTimer); syncPollTimer = null; }
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
    const tabId = tabStore.findByKey("persistent-email-list") || tabStore.active.id;
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

  // Save config on tab close + stop sync polling
  $effect(() => {
    return () => {
      config.flush();
      if (syncPollTimer) { clearTimeout(syncPollTimer); syncPollTimer = null; }
    };
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
    {syncProgress}
  />
</div>

{#if syncError}
  <div class="sync-error-banner" role="alert">
    <span class="sync-error-icon">⚠</span>
    <span class="sync-error-text">{syncError}</span>
  </div>
{/if}

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

<style>
  .email-list {
    display: flex;
    flex-direction: column;
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

  .sync-error-banner {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.75rem;
    background: #3a1a1a;
    border-bottom: 1px solid #6a2a2a;
    color: #e8a0a0;
    font-family: monospace;
    font-size: 0.78rem;
    animation: syncErrorFadeIn 0.2s ease;
  }
  .sync-error-icon {
    font-size: 0.9rem;
    flex-shrink: 0;
  }
  .sync-error-text {
    flex: 1;
    word-break: break-word;
  }
  @keyframes syncErrorFadeIn {
    from { opacity: 0; transform: translateY(-4px); }
    to { opacity: 1; transform: translateY(0); }
  }

</style>
