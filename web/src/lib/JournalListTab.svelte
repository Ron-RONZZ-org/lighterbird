<script>
  /** Journal entry list tab — selection, batch delete, UUID copy, search. */

  import { tabStore } from "./tabStore.svelte.js";
  import { journal as journalApi } from "./api.js";
  import {
    createSelectionManager,
    createCopyState,
    formatListItemDate,
    truncate,
    preview,
  } from "./listTabShared.svelte.js";

  let { data = {} } = $props();
  let entries = $derived(data?.entries || []);
  let total = $derived(data?.total || 0);

  // Shared copy state
  let uuidCopy = createCopyState();

  // Shared selection state (stable reference)
  let sel = createSelectionManager(
    () => entries,
    (uuid) => openEntry(uuid),
    async (uuids) => {
      await Promise.all(uuids.map((u) => journalApi.delete(u)));
    },
    () => refreshList(),
  );

  // Search bar
  let showSearch = $state(false);
  let searchQuery = $state("");
  let currentFilters = $state({});
  let searchTimeout;
  let abortController = null;

  // Sync state when tab data is replaced by a command
  $effect(() => {
    if (data && (data.filters !== undefined || data.query !== undefined)) {
      currentFilters = data.filters || {};
      searchQuery = data.query || "";
      showSearch = !!(data.query);
    }
  });

  async function openEntry(uuid) {
    if (!uuid) return;
    try {
      const entry = await journalApi.get(uuid);
      tabStore.open("status", entry.title || "(untitled)", entry, {
        idKey: `journal-${uuid}`,
        replaceable: false,
      });
    } catch (err) {
      tabStore.open("error", "Error", { message: err.message || "Failed to load entry" });
    }
  }

  async function deleteSelected() {
    const uuids = [...sel.selectedKeys];
    if (uuids.length === 0) return;
    try {
      await Promise.all(uuids.map((uuid) => journalApi.delete(uuid)));
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Delete Failed", {
        message: err.message || "Failed to delete entries",
      });
    }
  }

  /** Perform a search with the given query, preserving current filters. */
  function performSearch(query) {
    if (abortController) abortController.abort();
    abortController = new AbortController();

    const params = { ...currentFilters, limit: 50 };
    if (query && query.length >= 2) {
      params.query = query;
    }

    journalApi.list(params)
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
    document.querySelector(".journal-list .list")?.focus();
  }

  async function refreshList() {
    try {
      const params = { ...currentFilters, limit: 50 };
      if (searchQuery && searchQuery.length >= 2) {
        params.query = searchQuery;
      }
      const result = await journalApi.list(params);
      tabStore.update(tabStore.active.id, result);
    } catch { /* silent */ }
  }

  function handleWindowKeydown(e) {
    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) return;

    if (sel.confirmDelete) {
      if (e.key === "Escape") { sel.confirmDelete = false; e.preventDefault(); }
      return;
    }

    const plain = !e.ctrlKey && !e.metaKey && !e.altKey;
    switch (e.key) {
      case "/":
        if (plain) {
          showSearch = !showSearch;
          if (showSearch) requestAnimationFrame(() => document.querySelector(".journal-search-input")?.focus());
          else closeSearch();
          e.preventDefault();
        }
        return;
      case "Escape":
        if (showSearch) { closeSearch(); e.preventDefault(); return; }
        if (sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); return; }
        return;
    }

    sel.handleKeydown(e);
  }

  function handleNew() {
    tabStore.open("form", "Write Journal Entry", { form: "journal-write", initialData: {} }, {
      idKey: "journal-write",
    });
  }
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="journal-list">
  <!-- Toolbar -->
  <div class="toolbar" class:active={sel.selectionMode || sel.numSelected > 0}>
    {#if showSearch}
      <div class="search-bar">
        <span class="search-icon">🔍</span>
        <input
          type="text"
          class="journal-search-input"
          placeholder="Search entries… (min 2 chars)"
          value={searchQuery}
          oninput={handleSearchInput}
          onkeydown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); performSearch(searchQuery); }
            if (e.key === "Escape") { e.stopPropagation(); closeSearch(); }
          }}
          aria-label="Search journal entries"
        />
        {#if searchQuery}
          <button class="search-clear" onclick={() => { searchQuery = ""; performSearch(""); }} aria-label="Clear search">✕</button>
        {/if}
      </div>
    {:else if sel.selectionMode}
      <div class="toolbar-left">
        <button class="tool-btn" title="Exit selection mode (V)" onclick={() => sel.toggleSelectionMode()}>Exit <kbd>V</kbd></button>
      </div>
      <div class="toolbar-center">
        {#if sel.numSelected > 0}
          <span class="count">{sel.numSelected} selected</span>
        {:else}
          <span class="count muted">Select entries with click or <kbd>Space</kbd></span>
        {/if}
      </div>
      <div class="toolbar-right">
        <button class="tool-btn danger" disabled={sel.numSelected === 0} title="Delete selected (Delete key)"
          onclick={() => { sel.confirmDelete = true; }}>Delete <kbd>Del</kbd></button>
      </div>
    {:else}
      <div class="toolbar-left">
        <button class="tool-btn" title="Toggle selection mode (V)" onclick={() => sel.toggleSelectionMode()}>Select <kbd>V</kbd></button>
      </div>
      <div class="toolbar-center">
        <span class="search-hint"><kbd>/</kbd> search</span>
      </div>
      <div class="toolbar-right">
        <button class="tool-btn primary" onclick={handleNew} title="Write new journal entry">+ New</button>
      </div>
    {/if}
  </div>

  <!-- Entry list -->
  <div class="list" role="listbox" aria-label="Journal entries" aria-multiselectable="true">
    {#each entries as entry, i (entry.uuid)}
      <div
        id="row-{entry.uuid}"
        class="row"
        class:selected={sel.isSelected(entry.uuid)}
        class:focused={i === sel.focusedIndex}
        class:selection-mode={sel.selectionMode}
        role="option"
        aria-selected={sel.isSelected(entry.uuid)}
        tabindex={sel.selectionMode ? (i === sel.focusedIndex ? 0 : -1) : 0}
        onclick={(e) => sel.handleRowClick(e, entry.uuid)}
        onkeydown={(e) => {
          if (e.key === "Enter") sel.handleRowClick(e, entry.uuid);
        }}
      >
        <!-- Checkbox reserved space -->
        <span class="checkbox-cell">
          {#if sel.selectionMode}
            <span class="checkbox" class:checked={sel.isSelected(entry.uuid)}>
              {sel.isSelected(entry.uuid) ? "✓" : ""}
            </span>
          {/if}
        </span>

        <!-- Entry data -->
        <span class="journal-uuid" onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(entry.uuid); }}
              title="Click to copy UUID">
          {uuidCopy.copiedKey === entry.uuid ? "Copied!" : entry.uuid.slice(0, 8)}
        </span>
        <span class="date">{formatListItemDate(entry.date || entry.created_at)}</span>
        <span class="title">{truncate(entry.title || "(untitled)", 32)}</span>
        <span class="preview">{preview(entry.text || "")}</span>
      </div>
    {:else}
      <p class="empty">No journal entries.</p>
    {/each}
  </div>

  {#if sel.confirmDelete}
    <div class="confirm-dialog">
      <p>Delete {sel.numSelected} journal entr{sel.numSelected !== 1 ? 'ies' : 'y'}?</p>
      <div class="confirm-actions">
        <button class="btn-confirm" onclick={async () => { sel.confirmDelete = false; await deleteSelected(); }}>Delete</button>
        <button class="btn-cancel" onclick={() => { sel.confirmDelete = false; }}>Cancel</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .journal-list {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-family: monospace;
    font-size: 0.85rem;
    position: relative;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.3rem 0.5rem;
    background: #16162a;
    border-bottom: 1px solid #333;
    min-height: 2.2rem;
    flex-shrink: 0;
    font-family: monospace;
    font-size: 0.82rem;
  }
  .toolbar.active { background: #1a1a32; border-bottom-color: #4a4a6a; }
  .toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 0.5rem; }
  .toolbar-center { flex: 1; text-align: center; }

  .tool-btn {
    padding: 0.25rem 0.6rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #2a2a3e;
    color: #e0e0e0;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.8rem;
    transition: background 0.1s;
  }
  .tool-btn kbd {
    display: inline-block;
    padding: 0 3px;
    margin-left: 2px;
    font-family: monospace;
    font-size: 0.68rem;
    background: #222;
    border: 1px solid #555;
    border-radius: 3px;
    color: #999;
    line-height: 1.3;
  }
  .tool-btn:hover:not(:disabled) { background: #3a3a5e; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .tool-btn.danger:hover:not(:disabled) { background: #6b2020; border-color: #8b3030; }
  .tool-btn.primary { border-color: #3a6a3a; color: #7fdb7f; }
  .tool-btn.primary:hover { background: #1e3a1e; }

  .search-hint { color: #5a5a7a; font-size: 0.72rem; }
  .search-hint kbd {
    display: inline-block; padding: 0 3px; font-family: monospace;
    background: #222; border: 1px solid #444; border-radius: 3px; color: #888; font-size: 0.7rem;
  }

  .count { color: #7c7c9a; font-size: 0.82rem; }
  .count.muted { color: #555; }

  .search-bar {
    display: flex; align-items: center; gap: 0.4rem; flex: 1;
  }
  .search-icon { font-size: 0.75rem; opacity: 0.6; }
  .journal-search-input {
    flex: 1; padding: 0.3rem 0.4rem; border: 1px solid #444; border-radius: 4px;
    background: #12122a; color: #e0e0e0; font-family: monospace; font-size: 0.82rem; outline: none;
  }
  .journal-search-input:focus { border-color: #6a6a9a; }
  .journal-search-input::placeholder { color: #555; }
  .search-clear {
    background: none; border: none; color: #7c7c9a; cursor: pointer; font-size: 0.8rem; padding: 0.2rem;
  }
  .search-clear:hover { color: #e0e0e0; }

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
  .row:hover { background: #2a2a44; }
  .row.focused { background: #2a2a50; outline: 1px solid #5a5a8a; outline-offset: -1px; }
  .row.selected { background: #2a2a50; }
  .row.selection-mode { cursor: pointer; }

  .checkbox-cell {
    display: flex; align-items: center; justify-content: center;
    width: 1.8rem; flex-shrink: 0;
  }
  .checkbox {
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.1rem; height: 1.1rem;
    border: 1.5px solid #7c7c9a; border-radius: 3px;
    font-size: 0.7rem; color: #e0e0e0; background: transparent;
    transition: background 0.1s, border-color 0.1s;
  }
  .checkbox.checked { background: #4a6fa5; border-color: #4a6fa5; }

  .journal-uuid {
    color: var(--clr-muted);
    font-size: 0.72rem;
    min-width: 5rem;
    flex-shrink: 0;
    cursor: pointer;
  }
  .journal-uuid:hover { color: #7c7c9a; text-decoration: underline; }
  .date {
    color: var(--clr-muted);
    min-width: 6rem;
    flex-shrink: 0;
    font-size: 0.78rem;
  }
  .title {
    color: #e0e0e0;
    min-width: 10rem;
    flex-shrink: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .preview {
    color: #999;
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.8rem;
  }

  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }

  .confirm-dialog {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    background: rgba(0,0,0,0.6); z-index: 10;
  }
  .confirm-dialog p { color: #e0e0e0; font-size: 0.95rem; margin-bottom: 1rem; }
  .confirm-actions { display: flex; gap: 0.5rem; }
  .btn-confirm, .btn-cancel {
    padding: 0.4rem 1rem; border-radius: 4px; border: 1px solid #444;
    font-family: monospace; font-size: 0.85rem; cursor: pointer;
  }
  .btn-confirm { background: #6b2020; color: #e0e0e0; border-color: #8b3030; }
  .btn-cancel { background: #2a2a3e; color: #e0e0e0; }
</style>
