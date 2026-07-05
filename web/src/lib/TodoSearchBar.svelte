<script>
  let {
    showSearch = false,
    searchQuery = "",
    selectionMode = false,
    numSelected = 0,
    displayMode = "flat",
    sortOrder = "created",
    tagFilter = "",
    onToggleSelectionMode = () => {},
    onSearchInput = () => {},
    onSearchKeydown = () => {},
    onClearSearch = () => {},
    onCloseSearch = () => {},
    onNew = () => {},
    onImport = () => {},
    onExport = () => {},
    onDelete = () => {},
    onToggleMode = () => {},
    onSortChange = () => {},
    onTagFilterInput = () => {},
  } = $props();
</script>

<div class="toolbar" class:active={selectionMode || numSelected > 0}>
  {#if showSearch}
    <div class="search-bar">
      <span class="search-icon">&#x1F50D;</span>
      <input
        type="text"
        class="tl-search-input"
        placeholder="Search todos\u2026 (min 2 chars)"
        value={searchQuery}
        oninput={onSearchInput}
        onkeydown={onSearchKeydown}
        aria-label="Search todos"
      />
      {#if searchQuery}
        <button class="search-clear" onclick={onClearSearch} aria-label="Clear search">&#x2715;</button>
      {/if}
    </div>
  {:else if selectionMode}
    <div class="left">
      <button class="tool-btn" title="Exit selection mode (V)" onclick={onToggleSelectionMode}>
        Exit <kbd>V</kbd>
      </button>
    </div>
    <div class="center">
      {#if numSelected > 0}
        <span class="count">{numSelected} selected</span>
      {:else}
        <span class="count muted">Select todos with click or <kbd>Space</kbd></span>
      {/if}
    </div>
    <div class="right">
      <button class="tool-btn" disabled={numSelected === 0} title="Export selected (E)"
        onclick={onExport}>Export <kbd>E</kbd></button>
      <button class="tool-btn danger" disabled={numSelected === 0} title="Delete selected (Delete key)"
        onclick={onDelete}>Delete <kbd>Del</kbd></button>
    </div>
  {:else}
    <div class="left">
      <button class="tool-btn" title="Toggle selection mode (V)" onclick={onToggleSelectionMode}>Select <kbd>V</kbd></button>
      <button class="tool-btn" title="Toggle tree/flat view" onclick={onToggleMode}>
        {displayMode === "tree" ? "Flat" : "Tree"}
      </button>
      <label class="sort-label" title="Sort order">
        <select class="sort-select" value={sortOrder} onchange={onSortChange}>
          <option value="created">Newest</option>
          <option value="priority">Priority</option>
          <option value="due">Due date</option>
          <option value="title">Title</option>
        </select>
      </label>
    </div>
    <div class="center">
      <span class="hint"><kbd>/</kbd> search</span>
    </div>
    <div class="right">
      <button class="tool-btn primary" onclick={onNew} title="Add new todo">+ New <kbd>N</kbd></button>
      <button class="tool-btn" onclick={onImport} title="Import todos (M)">Import <kbd>M</kbd></button>
    </div>
  {/if}
</div>

<style>
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
  .sort-label { display: inline-flex; align-items: center; }
  .sort-select {
    padding: 0.15rem 0.3rem; border: 1px solid #444; border-radius: 3px;
    background: #2a2a3e; color: #c0c0e0; font-family: monospace; font-size: 0.72rem;
    cursor: pointer; outline: none;
  }
  .sort-select:focus { border-color: #6a6a9a; }
  .sort-select option { background: #1a1a2e; color: #e0e0e0; }
  .hint { color: #5a5a7a; font-size: 0.72rem; }
  .hint kbd {
    display: inline-block; padding: 0 3px; font-family: monospace;
    background: #222; border: 1px solid #444; border-radius: 3px; color: #888; font-size: 0.7rem;
  }
  .count { color: #7c7c9a; font-size: 0.82rem; }
  .count.muted { color: #555; }
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
</style>
