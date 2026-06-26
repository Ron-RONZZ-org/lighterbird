<script>
  /** Journal entry list tab — like EmailListTab but for journal entries. */

  import { tabStore } from "./tabStore.svelte.js";
  import { journal as journalApi } from "./api.js";

  let { data = {} } = $props();
  let entries = $derived(data?.entries || []);
  let total = $derived(data?.total || 0);

  let focusedIndex = $state(-1);
  let confirmDelete = $state(false);
  let selectedUuids = $state(new Set());
  let selectionMode = $state(false);
  let anchorIndex = $state(-1);
  let copiedUuid = $state("");

  function copyUuid(uuid) {
    navigator.clipboard.writeText(uuid).then(() => {
      copiedUuid = uuid;
      setTimeout(() => { if (copiedUuid === uuid) copiedUuid = ""; }, 1200);
    }).catch(() => {});
  }

  let numSelected = $derived(selectedUuids.size);

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

  function toggleSelectionMode() {
    selectionMode = !selectionMode;
    if (!selectionMode) {
      selectedUuids = new Set();
      focusedIndex = -1;
      anchorIndex = -1;
    } else if (entries.length > 0 && focusedIndex === -1) {
      focusedIndex = 0;
    }
  }

  function toggleEntry(uuid) {
    const next = new Set(selectedUuids);
    if (next.has(uuid)) next.delete(uuid);
    else next.add(uuid);
    selectedUuids = next;
  }

  function isSelected(uuid) {
    return selectedUuids.has(uuid);
  }

  function selectRange(from, to) {
    const start = Math.min(from, to);
    const end = Math.max(from, to);
    const next = new Set(selectedUuids);
    for (let i = start; i <= end; i++) {
      next.add(entries[i].uuid);
    }
    selectedUuids = next;
  }

  function handleRowClick(e, entry) {
    if (selectionMode) {
      if (e.shiftKey && anchorIndex >= 0) {
        const idx = entries.findIndex((en) => en.uuid === entry.uuid);
        if (idx >= 0) {
          selectRange(anchorIndex, idx);
          anchorIndex = idx;
        }
      } else {
        toggleEntry(entry.uuid);
        const idx = entries.findIndex((en) => en.uuid === entry.uuid);
        if (idx >= 0 && anchorIndex < 0) anchorIndex = idx;
      }
    } else {
      openEntry(entry.uuid);
    }
  }

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
    const uuids = [...selectedUuids];
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
        selectedUuids = new Set();
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
      selectedUuids = new Set();
    } catch {
      // Silent — let user retry
    }
  }

  function focusRow(index) {
    if (index < 0) index = 0;
    if (index >= entries.length) index = entries.length - 1;
    focusedIndex = index;
    const el = document.getElementById(`journal-row-${entries[index]?.uuid}`);
    if (el) el.scrollIntoView({ block: "nearest" });
  }

  function handleKeydown(e) {
    const tag = e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || e.target.isContentEditable) return;

    // When confirm dialog is open, block all keyboard events
    if (confirmDelete) {
      if (e.key === "Escape") { confirmDelete = false; e.preventDefault(); return; }
      if (e.key === "Enter") { e.preventDefault(); return; }
      return;
    }

    const plain = !e.ctrlKey && !e.metaKey && !e.altKey;
    switch (e.key) {
      case "v":
        if (plain) { toggleSelectionMode(); e.preventDefault(); }
        return;
      case "f":
        if (plain) {
          showSearch = !showSearch;
          if (showSearch) requestAnimationFrame(() => document.querySelector(".journal-search-input")?.focus());
          else closeSearch();
          e.preventDefault();
        }
        return;
      case "Escape":
        if (showSearch) { closeSearch(); e.preventDefault(); return; }
        if (selectionMode) { toggleSelectionMode(); e.preventDefault(); return; }
        return;
    }

    if (!selectionMode) return;
    const shift = e.shiftKey;

    function navRow(idx) {
      if (shift && anchorIndex >= 0) selectRange(anchorIndex, idx);
      focusRow(idx);
      if (!shift) anchorIndex = idx;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (focusedIndex < entries.length - 1) navRow(focusedIndex + 1);
        return;
      case "ArrowUp":
        e.preventDefault();
        if (focusedIndex > 0) navRow(focusedIndex - 1);
        return;
      case "PageDown":
        e.preventDefault();
        navRow(Math.min(focusedIndex + Math.max(1, Math.floor(entries.length / 5)), entries.length - 1));
        return;
      case "PageUp":
        e.preventDefault();
        navRow(Math.max(focusedIndex - Math.max(1, Math.floor(entries.length / 5)), 0));
        return;
      case "Home":
        e.preventDefault();
        if (shift && anchorIndex >= 0) selectRange(anchorIndex, 0);
        focusRow(0);
        if (!shift) anchorIndex = 0;
        return;
      case "End":
        e.preventDefault();
        if (shift && anchorIndex >= 0) selectRange(anchorIndex, entries.length - 1);
        focusRow(entries.length - 1);
        if (!shift) anchorIndex = entries.length - 1;
        return;
      case " ":
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < entries.length) {
          toggleEntry(entries[focusedIndex].uuid);
          if (anchorIndex < 0) anchorIndex = focusedIndex;
        }
        return;
      case "Delete":
        e.preventDefault();
        if (numSelected > 0) confirmDelete = true;
        return;
    }
  }

  function truncate(s, max) {
    if (!s) return "";
    return s.length > max ? s.slice(0, max - 1) + "…" : s;
  }

  function preview(s, max = 60) {
    if (!s) return "";
    // Take first line, strip markdown/whitespace
    const firstLine = s.split("\n")[0].trim();
    return truncate(firstLine.replace(/[#*_~`>]/g, ""), max);
  }

  function formatDate(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso.slice(0, 10);
      const now = new Date();
      const opts = d.toDateString() === now.toDateString()
        ? { hour: "2-digit", minute: "2-digit" }
        : d.getFullYear() === now.getFullYear()
          ? { month: "short", day: "numeric" }
          : { year: "numeric", month: "short", day: "numeric" };
      return d.toLocaleDateString([], opts);
    } catch { return iso.slice(0, 10); }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="journal-list">
  <!-- Toolbar -->
  <div class="toolbar" class:active={selectionMode || numSelected > 0}>
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
    {:else if selectionMode}
      <div class="toolbar-left">
        <button class="tool-btn" title="Exit selection mode (V)" onclick={toggleSelectionMode}>Exit <kbd>V</kbd></button>
      </div>
      <div class="toolbar-center">
        {#if numSelected > 0}
          <span class="count">{numSelected} selected</span>
        {:else}
          <span class="count muted">Select entries with click or <kbd>Space</kbd></span>
        {/if}
      </div>
      <div class="toolbar-right">
        <button class="tool-btn danger" disabled={numSelected === 0} title="Delete selected (Delete key)" onclick={() => { confirmDelete = true; }}>Delete <kbd>Del</kbd></button>
      </div>
    {:else}
      <div class="toolbar-left">
        <button class="tool-btn" title="Toggle selection mode (V)" onclick={toggleSelectionMode}>Select <kbd>V</kbd></button>
      </div>
      <div class="toolbar-center">
        <span class="search-hint"><kbd>f</kbd> search</span>
      </div>
      <div class="toolbar-right">
        <button class="tool-btn" onclick={() => { showSearch = !showSearch; requestAnimationFrame(() => document.querySelector(".journal-search-input")?.focus()); }}>🔍</button>
      </div>
    {/if}
  </div>

  <!-- Entry list -->
  <div class="list" role="listbox" aria-label="Journal entries" aria-multiselectable="true">
    {#each entries as entry, i (entry.uuid)}
      <div
        id="journal-row-{entry.uuid}"
        class="row"
        class:selected={isSelected(entry.uuid)}
        class:focused={i === focusedIndex}
        class:selection-mode={selectionMode}
        role="option"
        aria-selected={isSelected(entry.uuid)}
        tabindex={selectionMode ? (i === focusedIndex ? 0 : -1) : 0}
        onclick={(e) => handleRowClick(e, entry)}
        onkeydown={(e) => {
          if (e.key === "Enter") handleRowClick(e, entry);
        }}
      >
        <!-- Checkbox reserved space -->
        <span class="checkbox-cell">
          {#if selectionMode}
            <span class="checkbox" class:checked={isSelected(entry.uuid)}>
              {isSelected(entry.uuid) ? "✓" : ""}
            </span>
          {/if}
        </span>

        <!-- Entry data -->
        <span class="journal-uuid" onclick={(e) => { e.stopPropagation(); copyUuid(entry.uuid); }}
              title="Click to copy UUID">
          {copiedUuid === entry.uuid ? "Copied!" : entry.uuid.slice(0, 8)}
        </span>
        <span class="date">{formatDate(entry.date || entry.created_at)}</span>
        <span class="title">{truncate(entry.title || "(untitled)", 32)}</span>
        <span class="preview">{preview(entry.text || "")}</span>
      </div>
    {:else}
      <p class="empty">No journal entries.</p>
    {/each}
  </div>

  {#if confirmDelete}
    <div class="confirm-dialog">
      <p>Delete {numSelected} journal entr{numSelected !== 1 ? 'ies' : 'y'}?</p>
      <div class="confirm-actions">
        <button class="btn-confirm" onclick={async () => { confirmDelete = false; await deleteSelected(); }}>Delete</button>
        <button class="btn-cancel" onclick={() => { confirmDelete = false; }}>Cancel</button>
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
