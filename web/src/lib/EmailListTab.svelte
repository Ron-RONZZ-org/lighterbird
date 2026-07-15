<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi } from "./api.js";
  import { openMessage, openMessageInNewTab, handleRowClick, deleteSelected, hardDeleteSelected, moveSelected } from "./emailMessageOps.svelte.js";
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
  import SyncOverlay from "./SyncOverlay.svelte";
  import ScrollList from "@lightercore/ui/ScrollList.svelte";
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
    { key: "a", desc: "Open advanced search", category: "Email List" },
    { key: "m", desc: "Move selected messages", category: "Email List" },
    { key: "r", desc: "Restore from trash (selection mode, trash view)", category: "Email List" },
    { key: "l", desc: "Scroll to bottom of list", category: "Email List" },
    { key: "Ctrl+E", desc: "Export selected", modifiers: "Ctrl", category: "Email List" },
    { key: "Ctrl+M", desc: "Import .eml as draft (draft view)", modifiers: "Ctrl", category: "Email List" },
    { key: "Ctrl+R", desc: "Sync emails", modifiers: "Ctrl", category: "Email List" },
    { key: "Ctrl+Shift+Delete", desc: "Empty Trash (trash view)", modifiers: "Ctrl+Shift", category: "Email List" },
    { key: "Ctrl+Delete", desc: "Permanently delete selected", modifiers: "Ctrl", category: "Email List" },
  ]);

  let { data = {}, isTrashView: _isTrashViewProp = null, isDraftView: _isDraftViewProp = null } = $props();
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
  let _syncGuard = false;

  // ── Blocking initial sync on mount ──────────────────────────────
  let initialLoading = $state(true);

  async function handleInitialSync() {
    if (_syncGuard) return;
    _syncGuard = true;
    syncing = true;
    syncProgress = null;
    syncTaskId = null;
    syncError = "";

    try {
      const syncOpts = {};
      if (isTrashView) syncOpts.folderName = "Trash";
      const startResult = await emailApi.syncStart(null, syncOpts);
      syncTaskId = startResult.task_id;
      await pollUntilComplete();
    } catch (err) {
      syncError = `Sync failed: ${err?.message || "Unknown error"}`;
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
  // isTrashView / isDraftView are derived from the explicit prop (when
  // passed by TabView) or from initial data.  $derived ensures they stay
  // in sync when the user switches between tabs of different email-list
  // subtypes (email-list / email-trash-list / email-draft-list), because
  // EmailListTab stays mounted within the same {:else if} branch.
  let isTrashView = $derived(_isTrashViewProp !== null ? _isTrashViewProp : !!data?._isTrashView);
  let isDraftView = $derived(_isDraftViewProp !== null ? _isDraftViewProp : !!data?._isDraftView);

  // Own idKey for tab targeting.  Derived from stable isTrashView/isDraftView
  // so it survives safeUpdate (which strips _isTrashView/_isDraftView from data).
  let ownIdKey = $derived(
    isTrashView ? "persistent-email-trash-list"
    : isDraftView ? "persistent-email-draft-list"
    : "persistent-email-list"
  );

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
          case "/": if (plain) { showSearch = !showSearch; if (showSearch) requestAnimationFrame(() => document.querySelector(".search-input")?.focus()); else closeSearch(); e.preventDefault(); } return true;
          case "f": case "F": if (plain) { showFolderTree = !showFolderTree; e.preventDefault(); } return true;
          case "s": case "S": if (plain) { showSortDropdown = !showSortDropdown; e.preventDefault(); } return true;
          case "p": case "P": if (plain) { showParamsDialog = !showParamsDialog; e.preventDefault(); } return true;
          case "l": case "L": if (plain && hasMore) { loadMore(); e.preventDefault(); } return true;
          case "a": case "A": if (plain) { showAdvancedSearch = true; e.preventDefault(); } return true;
          case "m": case "M":
            if (plain && sel.numSelected > 0) { showMoveDialog = true; e.preventDefault(); }
            return true;
          case "r": case "R":
            if (plain && isTrashView && sel.selectionMode && sel.numSelected > 0) { handleRestoreSelected(); e.preventDefault(); }
            return true;
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
        // Ctrl+E: export selected
        if ((e.ctrlKey || e.metaKey) && e.key === "e") { e.preventDefault(); if (sel.numSelected > 0) openExportDialog(); return true; }
        // Ctrl+M: import draft (only in draft view)
        if ((e.ctrlKey || e.metaKey) && e.key === "m") { e.preventDefault(); if (isDraftView) openImportDialog(); return true; }
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "Delete" || e.key === "Del")) {
          // Ctrl+Shift+Delete: clear entire trash (only in trash view)
          e.preventDefault();
          if (isTrashView) {
            confirmClearTrash = true;
          }
          return true;
        }
        if ((e.ctrlKey || e.metaKey) && (e.key === "Delete" || e.key === "Del")) {
          e.preventDefault();
          if (sel.numSelected > 0) {
            confirmHardDelete = true;
          }
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
  let showAdvancedSearch = $state(false);
  let advancedSearchFilters = $state({});
  let searchKey = $state(0); // increment to trigger re-search
  let confirmHardDelete = $state(false);
  let confirmClearTrash = $state(false);

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

  /**
   * Handle click on a draft message — opens the compose form (email-send)
   * with the draft's fields pre-filled, instead of the read-only viewer.
   */
  function handleDraftClick(e, msg, sel) {
    if (sel.selectionMode) {
      sel.handleRowClick(e, msg.uuid);
      return;
    }
    // Parse to_recipients (JSON array) into a comma-separated string
    let toStr = "";
    try {
      const toArr = JSON.parse(msg.to_recipients || "[]");
      toStr = toArr.map((r) => r.email || r).join(", ");
    } catch { toStr = msg.to_recipients || ""; }
    let ccStr = "";
    try {
      const ccArr = JSON.parse(msg.cc_recipients || "[]");
      ccStr = ccArr.map((r) => r.email || r).join(", ");
    } catch { ccStr = msg.cc_recipients || ""; }

    tabStore.open(
      "form",
      "Compose Draft: " + (msg.subject || "(no subject)"),
      {
        form: "email-send",
        initialData: {
          account: msg.account_email || "",
          to: toStr,
          cc: ccStr,
          subject: msg.subject || "",
          body: msg.body || "",
          _returnIdKey: "persistent-email-list",
        },
      },
      { idKey: "email-compose" },
    );
  }

  $effect(() => {
    function handler() { showShortcutHelp = !showShortcutHelp; }
    window.addEventListener("help-toggle", handler);
    return () => window.removeEventListener("help-toggle", handler);
  });

  // Internal chunk size for cursor-based pagination — not a user-facing page.
  const _SEARCH_CHUNK = 100;

  let showSearch = $state(false);
  let searchQuery = $state("");
  let currentFilters = $state({});
  let searchTimeout;
  let abortController = null;
  // Continuous search: auto-fetches all matching results in the background
  // so the user can bulk-select/delete/move without pagination.
  let searchFetchingAll = $state(false);
  let searchFetchedTotal = $state(0);

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

  /**
   * Append unique results to the local messages array, deduplicating by uuid.
   * Updates hasMore / nextCursor for subsequent background fetches.
   */
  function appendUniqueResults(result) {
    const seen = new Set(messages.map((m) => m.uuid));
    const newMsgs = (result.messages || []).filter((m) => !seen.has(m.uuid));
    if (newMsgs.length > 0) {
      messages = [...messages, ...newMsgs];
    }
    hasMore = !!result.has_more;
    nextCursor = result.next_cursor || "";
    searchFetchedTotal = messages.length;
  }

  /**
   * Background loop: fetches all remaining search pages until exhausted.
   * Appends results silently — no user-facing pagination during search.
   */
  async function fetchAllSearchPages(query, extraFilters, signal) {
    searchFetchingAll = true;
    try {
      // Exhaust header-only (local SQL) pages first — they're fast
      while (nextCursor && !signal?.aborted) {
        const params = {
          ...currentFilters, ...filtersToApiParams(extraFilters || {}),
          query, header: "true", limit: _SEARCH_CHUNK, cursor: nextCursor,
        };
        const result = await emailApi.listMessages(params, signal);
        if (signal?.aborted) break;
        appendUniqueResults(result);
        if (!nextCursor) break;
      }
      // Single body-search shot (IMAP SEARCH, no cursor pagination)
      if (!signal?.aborted && query) {
        const bodyParams = {
          ...currentFilters, ...filtersToApiParams(extraFilters || {}),
          query, body: "true", limit: _SEARCH_CHUNK,
        };
        const bodyResult = await emailApi.listMessages(bodyParams, signal);
        if (!signal?.aborted) {
          appendUniqueResults(bodyResult);
        }
      }
    } catch { /* background search failures are non-fatal */ }
    finally { searchFetchingAll = false; }
  }

  function performSearch(query, extraFilters) {
    const tabId = tabStore.findByKey(ownIdKey) || tabStore.active.id;
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const signal = abortController.signal;

    // Free-text search from the search bar (/)
    if (query && query.length >= 2) {
      searchFetchingAll = false;
      searchFetchedTotal = 0;

      // Phase 1: headers only (fast, local SQL) — show results immediately
      const headerParams = {
        ...currentFilters, ...filtersToApiParams(extraFilters || {}),
        query, header: "true", limit: _SEARCH_CHUNK,
      };
      emailApi.listMessages(headerParams, signal)
        .then((result) => {
          if (signal.aborted) return;
          tabStore.safeUpdate(tabId, result);

          // Start background fetch for remaining header pages
          if (result.has_more) {
            fetchAllSearchPages(query, extraFilters, signal);
          }

          // Phase 2: body search (IMAP SEARCH, slower) — append additional
          const bodyParams = {
            ...currentFilters, ...filtersToApiParams(extraFilters || {}),
            query, body: "true", limit: _SEARCH_CHUNK,
          };
          emailApi.listMessages(bodyParams, signal)
            .then((bodyResult) => {
              if (signal.aborted) return;
              const merged = mergeSearchResults(result, bodyResult);
              tabStore.safeUpdate(tabId, merged);
            })
            .catch((err) => { if (err?.name !== "AbortError") throw err; });
        })
        .catch((err) => { if (err?.name !== "AbortError") throw err; });
    } else {
      // No free-text query: just send filters (advanced search case)
      const params = { ...currentFilters, ...filtersToApiParams(extraFilters || {}), limit: _SEARCH_CHUNK };
      if (params.header_text || params.body_text || Object.keys(params).length > 1) {
        emailApi.listMessages(params, signal)
          .then((result) => {
            if (signal.aborted) return;
            tabStore.safeUpdate(tabId, result);
          })
          .catch((err) => { if (err?.name !== "AbortError") throw err; });
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
    document.querySelector(".email-list-tab .list")?.focus();
  }

  async function refreshList() {
    // Resolve the owning list tab by its persistent idKey so the update
    // lands on the correct tab even if the user switched away during an
    // async operation (sync, search, pagination).  Fall back to the
    // currently active tab for non-list callers (delete, move).
    const tabId = tabStore.findByKey(ownIdKey) || tabStore.active.id;
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
      if (searchQuery && searchQuery.length >= 2) {
        params.query = searchQuery;
      }
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
      const syncOpts = {};
      if (isTrashView) syncOpts.folderName = "Trash";
      const startResult = await emailApi.syncStart(null, syncOpts);
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

  async function handleClearTrash() {
    confirmClearTrash = false;
    try {
      await emailApi.clearTrash();
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Clear Trash Failed", {
        message: err.message || "Failed to clear trash",
      });
    }
  }

  async function handleRestoreSelected() {
    const uuids = [...sel.selectedKeys];
    if (uuids.length === 0) return;
    try {
      await emailApi.batchMove(uuids, "INBOX");
      sel.toggleSelectionMode();
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Restore Failed", {
        message: err.message || "Failed to restore messages",
      });
    }
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
    const tabId = tabStore.findByKey(ownIdKey) || tabStore.active.id;
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

  // ── Trigger blocking initial sync on mount ─────────────────────
  $effect(() => {
    if (initialLoading) {
      handleInitialSync();
    }
    return () => {
      if (syncPollTimer) { clearTimeout(syncPollTimer); syncPollTimer = null; }
    };
  });

  // Save config on tab close + stop sync polling
  $effect(() => {
    return () => {
      config.flush();
    };
  });
</script>

<svelte:window onkeydown={handleWindowKeydown} />

{#if initialLoading && syncing}
  <SyncOverlay
    {syncProgress}
    title="Syncing email…"
    {syncError}
  />
{:else}
<div class="email-list-tab">
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
    onHardDelete={() => { if (sel.numSelected > 0) confirmHardDelete = true; }}
    onClearTrash={() => { if (isTrashView) confirmClearTrash = true; }}
    {isTrashView}
    {isDraftView}
    onRestore={handleRestoreSelected}
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
    {#if showSearch && searchQuery && searchFetchedTotal > 0}
      <div class="search-progress" role="status">
        {#if searchFetchingAll}
          <span class="search-progress-spinner">⟳</span>
          <span>Found {searchFetchedTotal} messages, searching for more…</span>
        {:else}
          <span class="search-progress-spinner" style="animation:none;">✓</span>
          <span>Search complete: {searchFetchedTotal} result{searchFetchedTotal !== 1 ? 's' : ''}</span>
        {/if}
      </div>
    {/if}
    <ScrollList
      items={messages}
      hasMore={hasMore}
      loading={loadingMore}
      getKey={(m) => m.uuid}
      onLoadMore={loadMore}
      emptyMessage="No messages."
    >
      {#snippet children(msg, i)}
        <EmailListRow
          {msg}
          index={i}
          isSelected={sel.isSelected(msg.uuid)}
          isFocused={i === sel.focusedIndex}
          selectionMode={sel.selectionMode}
          {uuidCopy}
          {emailCopy}
          onRowClick={(e, msg) => isDraftView ? handleDraftClick(e, msg, sel) : handleRowClick(e, msg, sel)}
        />
      {/snippet}
    </ScrollList>
  </div>

{#if sel.confirmDelete}
    <ConfirmDialog
      message="Delete {sel.numSelected} message{sel.numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { await sel.deleteSelected(); sel.confirmDelete = false; }}
      onDismiss={() => { sel.confirmDelete = false; }}
    />
  {/if}

  {#if confirmHardDelete}
    <ConfirmDialog
      message="Permanently delete {sel.numSelected} message{sel.numSelected !== 1 ? 's' : ''} from IMAP server and local DB? This cannot be undone."
      onConfirm={async () => {
        const uuids = [...sel.selectedKeys];
        confirmHardDelete = false;
        await hardDeleteSelected(uuids, () => refreshList());
      }}
      onDismiss={() => { confirmHardDelete = false; }}
    />
  {/if}

  {#if confirmClearTrash}
    <ConfirmDialog
      message="Empty Trash? This permanently deletes ALL messages in Trash folders from both IMAP server and local DB. This cannot be undone."
      onConfirm={handleClearTrash}
      onDismiss={() => { confirmClearTrash = false; }}
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
  {/if}

<style>
  .list {
    flex: 1;
    overflow-y: auto;
    padding: 0;
  }

  .search-progress {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.5rem;
    background: var(--clr-surface, #2a2a3e);
    border-top: 1px solid var(--clr-border, #4a4a6a);
    color: var(--clr-muted, #888);
    font-family: monospace;
    font-size: 0.78rem;
    animation: searchProgressFadeIn 0.2s ease;
  }
  .search-progress-spinner {
    display: inline-block;
    animation: searchProgressSpin 1s linear infinite;
  }
  @keyframes searchProgressSpin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  @keyframes searchProgressFadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
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
