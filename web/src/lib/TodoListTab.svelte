<script>
  /** Todo list tab — selection, batch delete, UUID copy, search, tree view. */

  import { tabStore } from "./tabStore.svelte.js";
  import { todo as todoApi } from "./api.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
  } from "./listTabShared.svelte.js";
  import { renderMarkdown } from "./markdown.js";
  import TodoListRow from "./TodoListRow.svelte";
  import TodoSearchBar from "./TodoSearchBar.svelte";
  import ExportDialog from "./ExportDialog.svelte";
  import ImportDialog from "./ImportDialog.svelte";

  let { data = {} } = $props();
  let todos = $derived(data?.todos || []);
  let total = $derived(data?.total || 0);
  let showSearch = $state(false);
  let searchQuery = $state("");
  let currentFilters = $state({});
  let searchTimeout;
  let abortController = null;
  let tagFilter = $state("");
  let sortOrder = $state("created");

  // Display mode: can be toggled between "flat" and "tree"
  // NOTE: initialized from data.tree to avoid circular dependency with isTree
  // svelte-ignore state_referenced_locally — intentionally captured at mount
  let displayMode = $state(data?.tree ? "tree" : "flat");
  let isTree = $derived(displayMode === "tree");

  // Sync displayMode with the incoming data
  $effect(() => {
    displayMode = data?.tree ? "tree" : "flat";
  });

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

  // Tree view state: set of expanded UUIDs
  let expanded = $state(new Set());

  function toggleExpand(uuid) {
    const next = new Set(expanded);
    if (next.has(uuid)) next.delete(uuid); else next.add(uuid);
    expanded = next;
  }

  function handleNew() {
    tabStore.open("form", "Add Todo", { form: "todo-add", initialData: {
      _returnIdKey: "persistent-todo-list",
      _returnType: "todo-list",
      _returnTitle: "Todos",
    } }, {
      idKey: "todo-add",
    });
  }

  // Shared selection state (stable reference — not $derived)
  let sel = createSelectionManager(
    () => todos,
    (uuid) => openTodo(uuid),
    async (uuids) => {
      await Promise.all(uuids.map((u) => todoApi.delete(u)));
    },
    () => refreshList(),
    { onNew: handleNew },
  );

  let uuidCopy = createCopyState();

  let showImportDialog = $state(false);
  let showExportDialog = $state(false);

  let exportItems = $derived(todos.filter(t => sel.selectedKeys.has(t.uuid)));

  function openImportDialog() {
    showImportDialog = true;
  }

  function openExportDialog() {
    showExportDialog = true;
  }

  /** Check if all ancestors of a tree item are expanded. */
  function isParentExpanded(todo, index, allTodos, expandedSet) {
    if (!todo._depth || todo._depth === 0) return true;
    for (let j = index - 1; j >= 0; j--) {
      const prev = allTodos[j];
      if (prev._depth < todo._depth) {
        if (!expandedSet.has(prev.uuid)) return false;
        return isParentExpanded(prev, j, allTodos, expandedSet);
      }
    }
    return true;
  }

  function getParentUuid(todo, allTodos, index) {
    for (let j = index - 1; j >= 0; j--) {
      if (allTodos[j]._depth < todo._depth) return allTodos[j].uuid;
    }
    return null;
  }

  // Sync filters from tab data
  $effect(() => {
    if (data && (data.filters !== undefined || data.query !== undefined)) {
      currentFilters = data.filters || {};
      searchQuery = data.query || "";
      showSearch = !!(data.query);
    }
  });

  async function openTodo(uuid) {
    if (!uuid) return;
    try {
      const item = await todoApi.get(uuid);
      tabStore.open("todo-view", item.title || "(untitled)", item, {
        idKey: `todo-${uuid}`,
        replaceable: false,
      });
    } catch (err) {
      tabStore.open("error", "Error", { message: err.message || "Failed to load todo" });
    }
  }

  /** Build the query params from current state. */
  function buildListParams() {
    const params = { ...currentFilters, limit: 50, sort: sortOrder };
    if (searchQuery && searchQuery.length >= 2) params.query = searchQuery;
    if (displayMode === "tree") params.tree = true;
    if (tagFilter) params.tags = tagFilter;
    return params;
  }

  async function refreshList() {
    const tabId = tabStore.active.id;
    try {
      const result = await todoApi.list(buildListParams());
      tabStore.safeUpdate(tabId, result);
    } catch { /* silent */ }
  }

  function toggleMode() {
    const newMode = displayMode === "tree" ? "flat" : "tree";
    displayMode = newMode;
    refreshList();
  }

  function performSearch(query) {
    const tabId = tabStore.active.id;
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const params = buildListParams();
    if (query && query.length >= 2) params.query = query;
    todoApi.list(params)
      .then((result) => { tabStore.safeUpdate(tabId, result); })
      .catch((err) => { if (err?.name === "AbortError") return; });
  }

  function handleSortChange(e) {
    sortOrder = e.target.value;
    refreshList();
  }

  function handleTagFilterInput(e) {
    tagFilter = e.target.value;
    refreshList();
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

  function priorityClass(p) {
    if (!p) return "";
    const n = typeof p === "string" ? parseInt(p, 10) : p;
    if (n >= 8) return "high";
    if (n >= 4) return "mid";
    return "low";
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
          if (showSearch) requestAnimationFrame(() => document.querySelector(".tl-search-input")?.focus());
          else closeSearch();
          e.preventDefault();
        }
        return;
      case "t":
        if (plain) { toggleMode(); e.preventDefault(); }
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

<div class="todo-list">
  <TodoSearchBar
    {showSearch}
    {searchQuery}
    selectionMode={sel.selectionMode}
    numSelected={sel.numSelected}
    {displayMode}
    {sortOrder}
    {tagFilter}
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
    onExport={openExportDialog}
    onDelete={() => { sel.confirmDelete = true; }}
    onToggleMode={toggleMode}
    onSortChange={handleSortChange}
    onTagFilterInput={handleTagFilterInput}
  />

  <!-- Todo list -->
  <div class="list" role="listbox" aria-label="Todos" aria-multiselectable="true">
    {#each todos as todo, i (todo.uuid)}
      <!-- In tree mode, skip items whose parent is collapsed -->
      {#if !isTree || todo._depth === 0 || isParentExpanded(todo, i, todos, expanded)}
        <TodoListRow
          {todo}
          {i}
          isSelected={sel.isSelected(todo.uuid)}
          isFocused={i === sel.focusedIndex}
          {highlight}
          {highlightActive}
          selectionMode={sel.selectionMode}
          {uuidCopy}
          {isTree}
          {expanded}
          onToggleExpand={toggleExpand}
          onRowClick={(e, key) => sel.handleRowClick(e, key)}
          {priorityClass}
        />
      {/if}
    {:else}
      <p class="empty">No todos.</p>
    {/each}
  </div>

  {#if sel.confirmDelete}
    <ConfirmDialog
      message="Delete {sel.numSelected} todo{sel.numSelected !== 1 ? 's' : ''}?"
      onConfirm={async () => { sel.confirmDelete = false; await sel.deleteSelected(); }}
      onDismiss={() => { sel.confirmDelete = false; }}
    />
  {/if}

  {#if showExportDialog}
    <ExportDialog
      domain="todo"
      items={exportItems}
      format="md"
      onClose={() => showExportDialog = false}
    />
  {/if}
  {#if showImportDialog}
    <ImportDialog
      domain="todo"
      format="md"
      onClose={() => showImportDialog = false}
    />
  {/if}
</div>

<style>
  .todo-list {
    display: flex; flex-direction: column; height: 100%;
    font-family: monospace; font-size: 0.85rem; position: relative;
  }
  .list { flex: 1; overflow-y: auto; padding: 0; }
  .empty { color: var(--clr-muted); text-align: center; padding: 2rem; }
</style>
