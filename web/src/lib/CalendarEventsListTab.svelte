<script>
  /** Calendar events list tab — selection, batch delete, UUID/title copy, search. */

  import { tabStore } from "./tabStore.svelte.js";
  import { calendar as calendarApi } from "./api.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
    formatListItemDate,
    truncate,
  } from "./listTabShared.svelte.js";

  let { data = {} } = $props();
  let events = $derived(data?.events || []);
  let total = $derived(data?.total || 0);

  // Highlight animation — auto-clears after 2s
  let highlight = $derived(data?.highlight || "");
  let highlightActive = $state(false);
  $effect(() => {
    if (highlight) {
      highlightActive = true;
      const timer = setTimeout(() => { highlightActive = false; }, 2000);
      return () => clearTimeout(timer);
    }
  });

  let showImportDialog = $state(false);
  let showExportDialog = $state(false);

  let exportItems = $derived(events.filter(e => sel.selectedKeys.has(e.uuid)));

  function openImportDialog() {
    showImportDialog = true;
  }

  function openExportDialog() {
    showExportDialog = true;
  }

  let showSearch = $state(false);
  let searchQuery = $state("");
  let currentFilters = $state({});
  let searchTimeout;
  let abortController = null;

  function handleNew() {
    tabStore.open("form", "Add Event", { form: "calendar-event-add", initialData: {
      _returnIdKey: "persistent-calendar-events",
      _returnType: "calendar-events",
      _returnTitle: "Events",
    } }, {
      idKey: "event-add",
    });
  }



  // Shared selection state (stable reference — not $derived)
  let sel = createSelectionManager(
    () => events,
    (uuid) => openEvent(uuid),
    async (uuids) => {
      await Promise.all(uuids.map((u) => calendarApi.deleteEvent(u)));
    },
    () => refreshList(),
    { onNew: handleNew },
  );

  let uuidCopy = createCopyState();

  // Sync filters from tab data
  $effect(() => {
    if (data && (data.filters !== undefined || data.query !== undefined)) {
      currentFilters = data.filters || {};
      searchQuery = data.query || "";
      showSearch = !!(data.query);
    }
  });

  async function openEvent(uuid) {
    if (!uuid) return;
    try {
      const evt = await calendarApi.getEvent(uuid);
      tabStore.open("events", evt.title || "(untitled)", { events: [evt] }, {
        idKey: `event-${uuid}`,
        replaceable: false,
      });
    } catch (err) {
      tabStore.open("error", "Error", { message: err.message || "Failed to load event" });
    }
  }

  async function refreshList() {
    try {
      const params = { ...currentFilters, limit: 50 };
      if (searchQuery && searchQuery.length >= 2) {
        params.query = searchQuery;
      }
      const result = await calendarApi.listEvents(params);
      tabStore.update(tabStore.active.id, result);
    } catch { /* silent */ }
  }

  function performSearch(query) {
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const params = { ...currentFilters, limit: 50 };
    if (query && query.length >= 2) params.query = query;
    calendarApi.listEvents(params)
      .then((result) => { tabStore.update(tabStore.active.id, result); })
      .catch((err) => { if (err?.name === "AbortError") return; });
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
  }

  function formatEventStart(event) {
    if (!event.start) return "";
    const s = event.start;
    if (s.length >= 16) return s.slice(0, 16);
    if (s.length >= 10) return s.slice(0, 10);
    return s;
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
      case "v":
        if (plain && !sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); }
        return;
      case "e":
        if (plain && sel.selectionMode && sel.numSelected > 0) {
          openExportDialog(); e.preventDefault();
        }
        return;
      case "/":
        if (plain) {
          showSearch = !showSearch;
          if (showSearch) requestAnimationFrame(() => document.querySelector(".cel-search-input")?.focus());
          else closeSearch();
          e.preventDefault();
        }
        return;
      case "Escape":
        if (showSearch) { closeSearch(); e.preventDefault(); return; }
        if (sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); return; }
        // No active UI state — close the tab
        tabStore.close(tabStore.active?.id);
        return;
    }
    sel.handleKeydown(e);
  }
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="calendar-events-list">
  <!-- Toolbar -->
  <div class="toolbar" class:active={sel.selectionMode || sel.numSelected > 0}>
    {#if showSearch}
      <div class="search-bar">
        <span class="search-icon">🔍</span>
        <input
          type="text"
          class="cel-search-input"
          placeholder="Search events… (min 2 chars)"
          value={searchQuery}
          oninput={handleSearchInput}
          onkeydown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); performSearch(searchQuery); }
            if (e.key === "Escape") { e.stopPropagation(); closeSearch(); }
          }}
          aria-label="Search events"
        />
        {#if searchQuery}
          <button class="search-clear" onclick={() => { searchQuery = ""; performSearch(""); }} aria-label="Clear search">✕</button>
        {/if}
      </div>
    {:else if sel.selectionMode}
      <div class="left">
        <button class="tool-btn" title="Exit selection mode (V)" onclick={() => sel.toggleSelectionMode()}>
          Exit <kbd>V</kbd>
        </button>
      </div>
      <div class="center">
        {#if sel.numSelected > 0}
          <span class="count">{sel.numSelected} selected</span>
        {:else}
          <span class="count muted">Select events with click or <kbd>Space</kbd></span>
        {/if}
      </div>
      <div class="right">
        <button class="tool-btn" disabled={sel.numSelected === 0} title="Export selected (E)"
          onclick={openExportDialog}>Export <kbd>E</kbd></button>
        <button class="tool-btn danger" disabled={sel.numSelected === 0} title="Delete selected (Delete key)"
          onclick={() => { sel.confirmDelete = true; }}>Delete <kbd>Del</kbd></button>
      </div>
    {:else}
      <div class="left">
        <button class="tool-btn" title="Toggle selection mode (V)" onclick={() => sel.toggleSelectionMode()}>Select <kbd>V</kbd></button>
      </div>
      <div class="center">
        <span class="hint"><kbd>/</kbd> search</span>
      </div>
      <div class="right">
        <button class="tool-btn primary" onclick={handleNew} title="Add new event">+ New <kbd>N</kbd></button>
        <button class="tool-btn" onclick={openImportDialog} title="Import events (M)">Import <kbd>M</kbd></button>
      </div>
    {/if}
  </div>

  <!-- Event list -->
  <div class="list" role="listbox" aria-label="Events" aria-multiselectable="true">
    {#each events as event, i (event.uuid)}
      <div
        id="row-{event.uuid}"
        class="row"
        class:selected={sel.isSelected(event.uuid)}
        class:focused={i === sel.focusedIndex}
        class:highlight={event.uuid === highlight && highlightActive}
        class:selection-mode={sel.selectionMode}
        role="option"
        aria-selected={sel.isSelected(event.uuid)}
        tabindex={sel.selectionMode ? (i === sel.focusedIndex ? 0 : -1) : 0}
        onclick={(e) => sel.handleRowClick(e, event.uuid)}
        onkeydown={(e) => { if (e.key === "Enter") sel.handleRowClick(e, event.uuid); }}
      >
        <span class="checkbox-cell">
          {#if sel.selectionMode}
            <span class="checkbox" class:checked={sel.isSelected(event.uuid)}>
              {sel.isSelected(event.uuid) ? "✓" : ""}
            </span>
          {/if}
        </span>

        <span class="euuid" role="button" tabindex="-1"
              onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(event.uuid); }}
              onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); uuidCopy.copyToClipboard(event.uuid); } }}
              title="Click to copy UUID">
          {uuidCopy.copiedKey === event.uuid ? "Copied!" : event.uuid.slice(0, 8)}
        </span>
        <span class="title">{truncate(event.title || "(untitled)", 30)}</span>
        <span class="start">{formatEventStart(event)}</span>
        <span class="location">{truncate(event.location || "", 16)}</span>
      </div>
    {:else}
      <p class="empty">No events.</p>
    {/each}
  </div>

  {#if sel.confirmDelete}
    <ConfirmDialog
      message="Delete {sel.numSelected} event{sel.numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { sel.confirmDelete = false; await sel.deleteSelected(); }}
      onDismiss={() => { sel.confirmDelete = false; }}
    />
  {/if}

  {#if showExportDialog}
    <ExportDialog
      domain="calendar"
      items={exportItems}
      format="ics"
      onClose={() => showExportDialog = false}
    />
  {/if}
  {#if showImportDialog}
    <ImportDialog
      domain="calendar"
      format="ics"
      onClose={() => showImportDialog = false}
    />
  {/if}
</div>

<style>
  .calendar-events-list {
    display: flex; flex-direction: column; height: 100%;
    font-family: monospace; font-size: 0.85rem; position: relative;
  }
  .toolbar {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.3rem 0.5rem; background: #16162a;
    border-bottom: 1px solid #333; min-height: 2.2rem;
    flex-shrink: 0; font-family: monospace; font-size: 0.82rem;
  }
  .toolbar.active { background: #1a1a32; border-bottom-color: #4a4a6a; }
  .left, .right { display: flex; align-items: center; gap: 0.5rem; }
  .center { flex: 1; text-align: center; }
  .tool-btn {
    padding: 0.25rem 0.6rem; border: 1px solid #444; border-radius: 4px;
    background: #2a2a3e; color: #e0e0e0; cursor: pointer;
    font-family: monospace; font-size: 0.8rem; transition: background 0.1s;
  }
  .tool-btn kbd {
    display: inline-block; padding: 0 3px; margin-left: 2px;
    font-family: monospace; font-size: 0.68rem; background: #222;
    border: 1px solid #555; border-radius: 3px; color: #999; line-height: 1.3;
  }
  .tool-btn:hover:not(:disabled) { background: #3a3a5e; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .tool-btn.danger:hover:not(:disabled) { background: #6b2020; border-color: #8b3030; }
  .tool-btn.primary { border-color: #3a6a3a; color: #7fdb7f; }
  .tool-btn.primary:hover { background: #1e3a1e; }
  .hint { color: #5a5a7a; font-size: 0.72rem; }
  .hint kbd {
    display: inline-block; padding: 0 3px; font-family: monospace;
    background: #222; border: 1px solid #444; border-radius: 3px; color: #888; font-size: 0.7rem;
  }
  .count { color: #7c7c9a; font-size: 0.82rem; }
  .count.muted { color: #555; }
  .search-bar { display: flex; align-items: center; gap: 0.4rem; flex: 1; }
  .search-icon { font-size: 0.75rem; opacity: 0.6; }
  .cel-search-input {
    flex: 1; padding: 0.3rem 0.4rem; border: 1px solid #444; border-radius: 4px;
    background: #12122a; color: #e0e0e0; font-family: monospace; font-size: 0.82rem; outline: none;
  }
  .cel-search-input:focus { border-color: #6a6a9a; }
  .cel-search-input::placeholder { color: #555; }
  .search-clear { background: none; border: none; color: #7c7c9a; cursor: pointer; font-size: 0.8rem; padding: 0.2rem; }
  .search-clear:hover { color: #e0e0e0; }
  .list { flex: 1; overflow-y: auto; padding: 0; }
  .row {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.4rem 0.5rem; border-bottom: 1px solid #2a2a3e;
    cursor: default; transition: background 0.08s; min-height: 2rem;
  }
  .row:hover { background: #2a2a44; }
  .row.focused { background: #2a2a50; outline: 1px solid #5a5a8a; outline-offset: -1px; }
  .row.selected { background: #2a2a50; }
  .row.highlight { animation: event-highlight-fade 2s ease-out; }
  @keyframes event-highlight-fade {
    0% { background: rgba(42, 90, 42, 0.6); }
    100% { background: transparent; }
  }
  .row.selection-mode { cursor: pointer; }
  .checkbox-cell { display: flex; align-items: center; justify-content: center; width: 1.8rem; flex-shrink: 0; }
  .checkbox {
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.1rem; height: 1.1rem; border: 1.5px solid #7c7c9a; border-radius: 3px;
    font-size: 0.7rem; color: #e0e0e0; background: transparent;
    transition: background 0.1s, border-color 0.1s;
  }
  .checkbox.checked { background: #4a6fa5; border-color: #4a6fa5; }
  .euuid {
    color: var(--clr-muted); font-size: 0.72rem; min-width: 5rem;
    flex-shrink: 0; cursor: pointer;
  }
  .euuid:hover { color: #7c7c9a; text-decoration: underline; }
  .title { color: #e0e0e0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .start { color: var(--clr-muted); min-width: 8rem; flex-shrink: 0; font-size: 0.78rem; }
  .location { color: #999; min-width: 6rem; flex-shrink: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .empty { color: var(--clr-muted); text-align: center; padding: 2rem; }
</style>
