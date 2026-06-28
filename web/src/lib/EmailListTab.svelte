<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { email as emailApi } from "./api.js";
  import EmailListToolbar from "./EmailListToolbar.svelte";
  import MoveDialog from "./MoveDialog.svelte";
  import KeyboardShortcutOverlay from "./KeyboardShortcutOverlay.svelte";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
    formatListItemDate,
    truncate,
  } from "./listTabShared.svelte.js";

  let { data = {} } = $props();
  let messages = $derived(data?.messages || []);
  let total = $derived(data?.total || 0);

  // Shared copy states
  let uuidCopy = createCopyState();
  let emailCopy = createCopyState();

  // Shared selection state (stable reference, not $derived)
  let sel = createSelectionManager(
    () => messages,
    (uuid) => openMessage(uuid),
    async (uuids) => {
      await emailApi.batchDelete(uuids);
    },
    () => refreshList(),
    {
      onBeforeKeydown(e) {
        // Handle search/help keys before delegating to selection manager
        const tag = e.target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) return true;

        // Move dialog open — only allow Escape
        if (showMoveDialog) {
          if (e.key === "Escape") { showMoveDialog = false; e.preventDefault(); }
          return true;
        }

        const plain = !e.ctrlKey && !e.metaKey && !e.altKey;
        switch (e.key) {
          case "f":
            if (plain) {
              showSearch = !showSearch;
              if (showSearch) requestAnimationFrame(() => document.querySelector(".search-input")?.focus());
              else closeSearch();
              e.preventDefault();
            }
            return true;
          case "Escape":
            if (showShortcutHelp) { showShortcutHelp = false; e.preventDefault(); return true; }
            if (showSearch) { closeSearch(); e.preventDefault(); return true; }
            if (showMoveDialog) { showMoveDialog = false; e.preventDefault(); return true; }
            return false; // Let selection manager handle it
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

  function handleNew() {
    tabStore.open("form", "Compose Email", { form: "email-send", initialData: {} }, {
      idKey: "email-compose",
    });
  }

  // Listen for global `h` key dispatched from TabView
  $effect(() => {
    function handler() { showShortcutHelp = !showShortcutHelp; }
    window.addEventListener("help-toggle", handler);
    return () => window.removeEventListener("help-toggle", handler);
  });

  // Search bar state
  let showSearch = $state(false);
  let searchQuery = $state("");
  let currentFilters = $state({});
  let searchTimeout;
  let abortController = null;

  // ── Row interaction ─────────────────────────────────────────────────

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

  // ── Batch actions ───────────────────────────────────────────────────

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

  // Sync state when tab data is replaced by a command (has filters/query).
  $effect(() => {
    if (data && (data.filters !== undefined || data.query !== undefined)) {
      currentFilters = data.filters || {};
      searchQuery = data.query || "";
      showSearch = !!(data.query);
    }
  });

  /** Perform a search with the given query, preserving current filters. */
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

  function handleWindowKeydown(e) {
    sel.handleKeydown(e);
  }
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="email-list">
  <!-- Toolbar -->
  <EmailListToolbar
    selectionMode={sel.selectionMode}
    numSelected={sel.numSelected}
    {showSearch}
    {searchQuery}
    onToggleMode={() => sel.toggleSelectionMode()}
    onDelete={() => { if (sel.numSelected > 0) sel.confirmDelete = true; }}
    onMove={() => { if (sel.numSelected > 0) showMoveDialog = true; }}
    onNew={handleNew}
    onToggleSearch={() => { showSearch = !showSearch; if (showSearch) requestAnimationFrame(() => document.querySelector(".search-input")?.focus()); }}
    onSearchInput={handleSearchInput}
    onSearchClear={() => { searchQuery = ""; performSearch(""); }}
    onSearchEscape={closeSearch}
    onSearchEnter={() => performSearch(searchQuery)}
  />

  <!-- Message list -->
  <div class="list" role="listbox" aria-label="Email messages" aria-multiselectable="true">
    {#each messages as msg, i (msg.uuid)}
      <div
        id="row-{msg.uuid}"
        class="row"
        class:selected={sel.isSelected(msg.uuid)}
        class:focused={i === sel.focusedIndex}
        class:selection-mode={sel.selectionMode}
        role="option"
        aria-selected={sel.isSelected(msg.uuid)}
        tabindex={sel.selectionMode ? (i === sel.focusedIndex ? 0 : -1) : 0}
        onclick={(e) => handleRowClick(e, msg)}
        onkeydown={(e) => {
          if (e.key === "Enter") handleRowClick(e, msg);
        }}
      >
        <!-- Checkbox (selection mode only, reserved space always) -->
        <span class="checkbox-cell">
          {#if sel.selectionMode}
            <span class="checkbox" class:checked={sel.isSelected(msg.uuid)}>
              {sel.isSelected(msg.uuid) ? "✓" : ""}
            </span>
          {/if}
        </span>

        <!-- Message data -->
        <span class="msg-uuid" onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(msg.uuid); }}
              title="Click to copy UUID">
          {uuidCopy.copiedKey === msg.uuid ? "Copied!" : msg.uuid.slice(0, 8)}
        </span>
        <span class="from" class:unread={!msg.is_read}
              onclick={(e) => {
                if (!sel.selectionMode) { e.stopPropagation(); emailCopy.copyToClipboard(msg.from || ""); }
              }}
              title="Click to copy email address">
          {emailCopy.copiedKey === msg.from ? "Copied!" : truncate(msg.from || "", 24)}
        </span>
        <span class="subject" class:unread={!msg.is_read}>{truncate(msg.subject || "(no subject)", 40)}</span>
        <span class="date">{formatListItemDate(msg.received_at)}</span>
      </div>
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

  <!-- Move dialog -->
  {#if showMoveDialog}
    <MoveDialog
      onConfirm={(destUuid) => handleMoveConfirmed(destUuid)}
      onDismiss={() => { showMoveDialog = false; }}
    />
  {/if}

  <!-- Keyboard shortcut help overlay -->
  {#if showShortcutHelp}
    <KeyboardShortcutOverlay onDismiss={() => { showShortcutHelp = false; }} />
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

  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.5rem;
    border-bottom: 1px solid #2a2a3e;
    cursor: default;
    transition: background 0.08s;
    min-height: 2rem;
  }
  .row:hover {
    background: #2a2a44;
  }
  .row.focused {
    background: #2a2a50;
    outline: 1px solid #5a5a8a;
    outline-offset: -1px;
  }
  .row.selected {
    background: #2a2a50;
  }
  .row.selection-mode {
    cursor: pointer;
  }

  /* Checkbox cell — always reserved to avoid layout shift */
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
    transition: background 0.1s, border-color 0.1s;
  }
  .checkbox.checked {
    background: #4a6fa5;
    border-color: #4a6fa5;
  }

  .msg-uuid {
    color: var(--clr-muted);
    font-size: 0.72rem;
    min-width: 5rem;
    flex-shrink: 0;
    cursor: pointer;
  }
  .msg-uuid:hover { color: #7c7c9a; text-decoration: underline; }
  .from {
    color: #e0e0e0;
    min-width: 10rem;
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    cursor: pointer;
  }
  .from:hover { color: #ccc; text-decoration: underline; }
  .from.unread {
    font-weight: 700;
  }
  .subject {
    color: #ccc;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .subject.unread {
    font-weight: 600;
    color: #e0e0e0;
  }
  .date {
    color: var(--clr-muted);
    min-width: 6rem;
    text-align: right;
    flex-shrink: 0;
    font-size: 0.78rem;
  }

  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }
</style>
