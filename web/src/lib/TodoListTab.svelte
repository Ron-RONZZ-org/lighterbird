<script>
  /** Todo list tab — selection, batch delete, UUID copy, search, tree view. */

  import { tabStore } from "./tabStore.svelte.js";
  import { todo as todoApi } from "./api.js";
  import ConfirmDialog from "./ConfirmDialog.svelte";
  import {
    createSelectionManager,
    createCopyState,
    formatListItemDate,
    truncate,
  } from "./listTabShared.svelte.js";
  import { renderMarkdown } from "./markdown.js";

  let { data = {} } = $props();
  let todos = $derived(data?.todos || []);
  let total = $derived(data?.total || 0);
  let isTree = $derived(!!data?.tree);

  let showSearch = $state(false);
  let searchQuery = $state("");
  let currentFilters = $state({});
  let searchTimeout;
  let abortController = null;

  // Tree view state: set of expanded UUIDs
  let expanded = $state(new Set());

  function toggleExpand(uuid) {
    const next = new Set(expanded);
    if (next.has(uuid)) next.delete(uuid); else next.add(uuid);
    expanded = next;
  }

  function handleNew() {
    tabStore.open("form", "Add Todo", { form: "todo-add", initialData: {} }, {
      idKey: "todo-add",
    });
  }

  // Auto-add form via commandRouter interception
  $effect(() => {
    if (data?.autoAdd && data?.addFormType === "todo-add") {
      handleNew();
    }
  });

  // Shared selection state (stable reference — not $derived)
  let sel = createSelectionManager(
    () => todos,
    (uuid) => openTodo(uuid),
    async (uuids) => {
      await Promise.all(uuids.map((u) => todoApi.delete(u)));
    },
    () => refreshList(),
  );

  let uuidCopy = createCopyState();

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

  async function refreshList() {
    try {
      const params = { ...currentFilters, limit: 50 };
      if (searchQuery && searchQuery.length >= 2) {
        params.query = searchQuery;
      }
      if (isTree) params.tree = true;
      const result = await todoApi.list(params);
      tabStore.update(tabStore.active.id, result);
    } catch { /* silent */ }
  }

  function performSearch(query) {
    if (abortController) abortController.abort();
    abortController = new AbortController();
    const params = { ...currentFilters, limit: 50 };
    if (query && query.length >= 2) params.query = query;
    if (isTree) params.tree = true;
    todoApi.list(params)
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
      case "f":
        if (plain) {
          showSearch = !showSearch;
          if (showSearch) requestAnimationFrame(() => document.querySelector(".tl-search-input")?.focus());
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
</script>

<svelte:window onkeydown={handleWindowKeydown} />

<div class="todo-list">
  <!-- Toolbar -->
  <div class="toolbar" class:active={sel.selectionMode || sel.numSelected > 0}>
    {#if showSearch}
      <div class="search-bar">
        <span class="search-icon">🔍</span>
        <input
          type="text"
          class="tl-search-input"
          placeholder="Search todos… (min 2 chars)"
          value={searchQuery}
          oninput={handleSearchInput}
          onkeydown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); performSearch(searchQuery); }
            if (e.key === "Escape") { e.stopPropagation(); closeSearch(); }
          }}
          aria-label="Search todos"
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
          <span class="count muted">Select todos with click or <kbd>Space</kbd></span>
        {/if}
      </div>
      <div class="right">
        <button class="tool-btn danger" disabled={sel.numSelected === 0} title="Delete selected (Delete key)"
          onclick={() => { sel.confirmDelete = true; }}>Delete <kbd>Del</kbd></button>
      </div>
    {:else}
      <div class="left">
        <button class="tool-btn" title="Toggle selection mode (V)" onclick={() => sel.toggleSelectionMode()}>Select <kbd>V</kbd></button>
        {#if isTree}
          <span class="tree-indicator">[tree]</span>
        {/if}
      </div>
      <div class="center">
        <span class="hint"><kbd>f</kbd> search</span>
      </div>
      <div class="right">
        <button class="tool-btn primary" onclick={handleNew} title="Add new todo">+ New</button>
      </div>
    {/if}
  </div>

  <!-- Todo list -->
  <div class="list" role="listbox" aria-label="Todos" aria-multiselectable="true">
    {#each todos as todo, i (todo.uuid)}
      <!-- In tree mode, skip items whose parent is collapsed -->
      {#if !isTree || todo._depth === 0 || isParentExpanded(todo, i, todos, expanded)}
          <div
            id="row-{todo.uuid}"
            class="row"
            class:selected={sel.isSelected(todo.uuid)}
            class:focused={i === sel.focusedIndex}
            class:selection-mode={sel.selectionMode}
            class:done={todo.status === "done"}
            class:tree-mode={isTree}
            style={isTree ? `padding-left: ${0.5 + (todo._depth || 0) * 1.5}rem` : ""}
            role="option"
            aria-selected={sel.isSelected(todo.uuid)}
            tabindex={sel.selectionMode ? (i === sel.focusedIndex ? 0 : -1) : 0}
            onclick={(e) => sel.handleRowClick(e, todo.uuid)}
            onkeydown={(e) => { if (e.key === "Enter") sel.handleRowClick(e, todo.uuid); }}
          >
            <span class="checkbox-cell">
              {#if sel.selectionMode}
                <span class="checkbox" class:checked={sel.isSelected(todo.uuid)}>
                  {sel.isSelected(todo.uuid) ? "✓" : ""}
                </span>
              {/if}
            </span>

            {#if isTree}
              <span class="tree-toggle-cell">
                {#if todo._has_children}
                  <button class="tree-toggle"
                    onclick={(e) => { e.stopPropagation(); toggleExpand(todo.uuid); }}
                    aria-label={expanded.has(todo.uuid) ? "Collapse" : "Expand"}>
                    {expanded.has(todo.uuid) ? "▼" : "▶"}
                  </button>
                {:else}
                  <span class="tree-toggle-placeholder"></span>
                {/if}
              </span>
            {/if}

            <span class="tuuid" onclick={(e) => { e.stopPropagation(); uuidCopy.copyToClipboard(todo.uuid); }}
                  title="Click to copy UUID">
              {uuidCopy.copiedKey === todo.uuid ? "Copied!" : todo.uuid.slice(0, 8)}
            </span>
            <span class="title">{truncate(todo.title || "(untitled)", 32)}</span>
            <span class="priority {priorityClass(todo.priority)}">{todo.priority || ""}</span>
            <span class="due">{formatListItemDate(todo.due)}</span>
            <span class="status">{todo.status === "done" ? "✓ done" : "○"}</span>
          </div>
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
</div>

<style>
  .todo-list {
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
  .tree-indicator { color: var(--clr-muted); font-size: 0.72rem; font-style: italic; }
  .search-bar { display: flex; align-items: center; gap: 0.4rem; flex: 1; }
  .search-icon { font-size: 0.75rem; opacity: 0.6; }
  .tl-search-input {
    flex: 1; padding: 0.3rem 0.4rem; border: 1px solid #444; border-radius: 4px;
    background: #12122a; color: #e0e0e0; font-family: monospace; font-size: 0.82rem; outline: none;
  }
  .tl-search-input:focus { border-color: #6a6a9a; }
  .tl-search-input::placeholder { color: #555; }
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
  .row.selection-mode { cursor: pointer; }
  .row.done .title { opacity: 0.5; text-decoration: line-through; }
  .checkbox-cell {
    display: flex; align-items: center; justify-content: center;
    width: 1.8rem; flex-shrink: 0;
  }
  .checkbox {
    display: inline-flex; align-items: center; justify-content: center;
    width: 1.1rem; height: 1.1rem; border: 1.5px solid #7c7c9a; border-radius: 3px;
    font-size: 0.7rem; color: #e0e0e0; background: transparent;
    transition: background 0.1s, border-color 0.1s;
  }
  .checkbox.checked { background: #4a6fa5; border-color: #4a6fa5; }
  .tree-toggle-cell {
    display: flex; align-items: center; justify-content: center;
    width: 1.2rem; flex-shrink: 0;
  }
  .tree-toggle {
    background: none; border: 1px solid transparent; color: var(--clr-muted);
    cursor: pointer; padding: 0; font-size: 0.55rem; width: 1.2rem; height: 1.2rem;
    display: flex; align-items: center; justify-content: center;
    border-radius: 3px; transition: all 0.1s;
  }
  .tree-toggle:hover {
    color: #e0e0e0; border-color: #4a4a6a; background: #2a2a3e;
  }
  .tree-toggle-placeholder { width: 1.2rem; }
  .tuuid {
    color: var(--clr-muted); font-size: 0.72rem; min-width: 5rem;
    flex-shrink: 0; cursor: pointer;
  }
  .tuuid:hover { color: #7c7c9a; text-decoration: underline; }
  .title { color: #e0e0e0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .priority { font-size: 0.75rem; min-width: 2rem; text-align: center; flex-shrink: 0; }
  .priority.high { color: #e07070; }
  .priority.mid { color: #d0b060; }
  .priority.low { color: var(--clr-muted); }
  .due { color: var(--clr-muted); min-width: 6rem; flex-shrink: 0; font-size: 0.78rem; }
  .status { color: var(--clr-muted); min-width: 3rem; flex-shrink: 0; text-align: right; }
  .empty { color: var(--clr-muted); text-align: center; padding: 2rem; }
</style>
