<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { letters as lettersApi } from "./api.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
  } from "./listTabShared.svelte.js";
  import LetterListRow from "./LetterListRow.svelte";
  import LetterSearchBar from "./LetterSearchBar.svelte";
  import ExportDialog from "./ExportDialog.svelte";
  import ImportDialog from "./ImportDialog.svelte";

  let { data = {} } = $props();
  let letters = $derived(data?.letters || []);
  let total = $derived(data?.total || 0);

  let uuidCopy = createCopyState();

  let sel = createSelectionManager(
    () => letters,
    (uuid) => openLetter(uuid),
    async (uuids) => {
      await Promise.all(uuids.map((u) => lettersApi.delete(u)));
    },
    () => refreshList(),
    { onNew: handleNew },
  );

  let showImportDialog = $state(false);
  let showExportDialog = $state(false);

  let exportItems = $derived(letters.filter(l => sel.selectedKeys.has(l.uuid)));

  function openImportDialog() {
    showImportDialog = true;
  }

  function openExportDialog() {
    showExportDialog = true;
  }

  let highlight = $derived(data?.highlight || "");
  let highlightActive = $state(false);
  $effect(() => {
    if (highlight) {
      highlightActive = true;
      const timer = setTimeout(() => { highlightActive = false; }, 2000);
      return () => clearTimeout(timer);
    }
  });

  let showSearch = $state(false);
  let showSortDropdown = $state(false);
  let showTagFilter = $state(false);
  let tagFilterEntries = $state([]);
  let searchQuery = $state("");
  let currentFilters = $state({});
  let searchTimeout;
  let abortController = null;

  $effect(() => {
    if (data && (data.filters !== undefined || data.query !== undefined)) {
      currentFilters = data.filters || {};
      searchQuery = data.query || "";
      showSearch = !!(data.query);
    }
  });

  async function openLetter(uuid) {
    if (!uuid) return;
    try {
      const letterData = await lettersApi.get(uuid);
      const bodyData = await lettersApi.getBody(uuid);
      tabStore.open("letter-view", letterData.object || "(untitled)", { letter: letterData, body: bodyData.body }, {
        idKey: `letter-${uuid}`,
        replaceable: false,
      });
    } catch (err) {
      tabStore.open("error", "Error", { message: err.message || "Failed to load letter" });
    }
  }

  async function deleteSelected() {
    const uuids = [...sel.selectedKeys];
    if (uuids.length === 0) return;
    try {
      await Promise.all(uuids.map((uuid) => lettersApi.delete(uuid)));
      await refreshList();
    } catch (err) {
      tabStore.open("error", "Delete Failed", {
        message: err.message || "Failed to delete letters",
      });
    }
  }

  function performSearch(query) {
    const tabId = tabStore.active.id;
    if (abortController) abortController.abort();
    abortController = new AbortController();

    const params = { ...currentFilters, limit: 50 };
    if (query && query.length >= 2) {
      params.query = query;
    }
    if (tagFilterEntries.length > 0) {
      params.tag = tagFilterEntries.join(",");
    }

    lettersApi.list(params)
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
    document.querySelector(".letter-list .list")?.focus();
  }

  async function refreshList() {
    const tabId = tabStore.active.id;
    try {
      const params = { ...currentFilters, limit: 50 };
      if (searchQuery && searchQuery.length >= 2) {
        params.query = searchQuery;
      }
      if (tagFilterEntries.length > 0) {
        params.tag = tagFilterEntries.join(",");
      }
      const result = await lettersApi.list(params);
      tabStore.safeUpdate(tabId, result);
    } catch { /* silent */ }
  }

  function handleSortChange(sort) {
    currentFilters = { ...currentFilters, sort };
    refreshList();
  }

  function handleGroupChange(enabled) {
    currentFilters = { ...currentFilters, group: enabled ? "conversation" : "" };
    refreshList();
  }

  function onTagFilterChange() {
    performSearch(searchQuery);
  }

  function clearTagFilter() {
    tagFilterEntries = [];
    performSearch(searchQuery);
    showTagFilter = false;
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
      case "e":
        if (plain && sel.selectionMode && sel.numSelected > 0) {
          openExportDialog(); e.preventDefault();
        }
        return;
      case "/":
        if (plain) {
          showSearch = !showSearch;
          if (showSearch) requestAnimationFrame(() => document.querySelector(".letter-search-input")?.focus());
          else closeSearch();
          e.preventDefault();
        }
        return;
      case "s":
      case "S":
        if (plain) { showSortDropdown = !showSortDropdown; e.preventDefault(); }
        return;
      case "f":
      case "F":
        if (plain) { showTagFilter = !showTagFilter; e.preventDefault(); }
        return;
      case "Escape":
        if (showSortDropdown) { showSortDropdown = false; e.preventDefault(); return; }
        if (showTagFilter) { showTagFilter = false; e.preventDefault(); return; }
        if (showSearch) { closeSearch(); e.preventDefault(); return; }
        if (sel.selectionMode) { sel.toggleSelectionMode(); e.preventDefault(); return; }
        // No active UI state — close the tab
        tabStore.close(tabStore.active?.id);
        return;
    }

    sel.handleKeydown(e);
  }

  function handleNew() {
    tabStore.open("form", "Add Letter", { form: "letter-add", initialData: {
      _returnIdKey: "persistent-letter-list",
      _returnType: "letter-list",
      _returnTitle: "Letters",
    } }, {
      idKey: "letter-add",
    });
  }
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="letter-list">
  <LetterSearchBar
    {showSearch}
    {searchQuery}
    selectionMode={sel.selectionMode}
    numSelected={sel.numSelected}
    onToggleSelectionMode={() => sel.toggleSelectionMode()}
    onSearchInput={handleSearchInput}
    onSearchKeydown={(e) => {
      if (e.key === "Enter") { e.preventDefault(); performSearch(searchQuery); }
      if (e.key === "Escape") { e.stopPropagation(); closeSearch(); }
    }}
    onClearSearch={() => { searchQuery = ""; performSearch(""); }}
    onCloseSearch={closeSearch}
    onNew={handleNew}
    onImport={openImportDialog}
    onSend={() => {
      tabStore.open("form", "Send Letter", { form: "letter-send", initialData: {
        _returnIdKey: "persistent-letter-list",
        _returnType: "letter-list",
        _returnTitle: "Letters",
      } }, { idKey: "letter-send" });
    }}
    onExport={openExportDialog}
    onDelete={() => { sel.confirmDelete = true; }}
    {currentFilters}
    onSortChange={handleSortChange}
    onGroupChange={handleGroupChange}
    bind:tagFilterEntries
    onTagFilterChange={onTagFilterChange}
    onClearTagFilter={clearTagFilter}
    bind:showSortDropdown
    bind:showTagFilter
    onToggleSort={() => { showSortDropdown = !showSortDropdown; }}
    onToggleTagFilter={() => { showTagFilter = !showTagFilter; }}
    onCloseSort={() => { showSortDropdown = false; }}
    onCloseTagFilter={() => { showTagFilter = false; }}
  />

  <div class="list" role="listbox" aria-label="Letters" aria-multiselectable="true">
    {#each letters as letter, i (letter.uuid)}
      <LetterListRow
        {letter}
        {i}
        isSelected={sel.isSelected(letter.uuid)}
        isFocused={i === sel.focusedIndex}
        {highlight}
        {highlightActive}
        selectionMode={sel.selectionMode}
        {uuidCopy}
        onRowClick={(e, key) => sel.handleRowClick(e, key)}
      />
    {:else}
      <p class="empty">No letters.</p>
    {/each}
  </div>

  {#if sel.confirmDelete}
    <ConfirmDialog
      message="Delete {sel.numSelected} letter{sel.numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { sel.confirmDelete = false; await deleteSelected(); }}
      onDismiss={() => { sel.confirmDelete = false; }}
    />
  {/if}

  {#if showExportDialog}
    <ExportDialog
      domain="letter"
      items={exportItems}
      format="md"
      onClose={() => showExportDialog = false}
    />
  {/if}
  {#if showImportDialog}
    <ImportDialog
      domain="letter"
      format="md"
      onClose={() => showImportDialog = false}
    />
  {/if}
</div>

<style>
  .letter-list {
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
</style>
