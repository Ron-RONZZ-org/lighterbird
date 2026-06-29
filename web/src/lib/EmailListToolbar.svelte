<script>
  let {
    selectionMode = false,
    numSelected = 0,
    showSearch = false,
    searchQuery = "",
    showFolderTree = false,
    showSortDropdown = false,
    showParamsDialog = false,
    onToggleMode = () => {},
    onDelete = () => {},
    onMove = () => {},
    onNew = null,
    onToggleSearch = () => {},
    onSearchInput = () => {},
    onSearchClear = () => {},
    onSearchEscape = () => {},
    onSearchEnter = () => {},
    onToggleFolderTree = () => {},
    onToggleSortDropdown = () => {},
    onToggleParamsDialog = () => {},
  } = $props();

  function handleSearchKeydown(e) {
    if (e.key === "Enter") {
      e.preventDefault();
      onSearchEnter();
    }
    if (e.key === "Escape") {
      e.stopPropagation();
      onSearchEscape();
    }
  }
</script>

<div class="toolbar" class:active={selectionMode || numSelected > 0}>
  {#if showSearch}
    <!-- Search mode: full-width input -->
    <div class="search-bar">
      <span class="search-icon">🔍</span>
      <input
        type="text"
        class="search-input"
        placeholder="Search messages… (min 2 chars)"
        value={searchQuery}
        oninput={onSearchInput}
        onkeydown={handleSearchKeydown}
        aria-label="Search messages"
      />
      {#if searchQuery}
        <button class="search-clear" onclick={onSearchClear} aria-label="Clear search">✕</button>
      {/if}
    </div>
  {:else if selectionMode}
    <!-- Selection mode: action toolbar -->
    <div class="left">
      <button class="tool-btn" title="Exit selection mode (V)" onclick={onToggleMode}>
        Exit <kbd>V</kbd>
      </button>
    </div>
    <div class="center">
      {#if numSelected > 0}
        <span class="count">{numSelected} selected</span>
      {:else}
        <span class="count muted">Select messages with click or <kbd>Space</kbd></span>
      {/if}
    </div>
    <div class="right">
      <button class="tool-btn" disabled={numSelected === 0} onclick={onMove} title="Move selected (Ctrl+M)">Move <kbd>⌃M</kbd></button>
      <button class="tool-btn danger" disabled={numSelected === 0} onclick={onDelete} title="Delete selected (Delete key)">Delete <kbd>Del</kbd></button>
    </div>
  {:else}
    <!-- View mode: expanded toolbar with actions + nav -->
    <div class="left">
      <button class="tool-btn" title="Toggle selection mode (V)" onclick={onToggleMode}>Select <kbd>V</kbd></button>
      <button class="tool-btn" title="Folders (F)" onclick={onToggleFolderTree}
        class:active={showFolderTree}>Fldrs <kbd>F</kbd></button>
      <button class="tool-btn" title="Sort (S)" onclick={onToggleSortDropdown}
        class:active={showSortDropdown}>Sort <kbd>S</kbd></button>
      <button class="tool-btn" title="Parameters (P)" onclick={onToggleParamsDialog}
        class:active={showParamsDialog}>Params <kbd>P</kbd></button>
    </div>
    <div class="center">
      <span class="search-hint"><kbd>/</kbd> search</span>
    </div>
    <div class="right">
      {#if onNew}
        <button class="tool-btn primary" onclick={onNew} title="New message">+ New <kbd>N</kbd></button>
      {/if}
    </div>
  {/if}
</div>

<style>
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
  .toolbar.active {
    background: #1a1a32;
    border-bottom-color: #4a4a6a;
  }

  .left, .right {
    display: flex;
    align-items: center;
    gap: 0.3rem;
  }
  .center {
    flex: 1;
    text-align: center;
  }

  .tool-btn {
    padding: 0.25rem 0.6rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #2a2a3e;
    color: #e0e0e0;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.78rem;
    transition: background 0.1s, border-color 0.1s;
    white-space: nowrap;
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
  .tool-btn.active { border-color: #6a6a9a; background: #2a2a50; }
  .tool-btn.danger:hover:not(:disabled) { background: #6b2020; border-color: #8b3030; }
  .tool-btn.primary { border-color: #3a6a3a; color: #7fdb7f; }
  .tool-btn.primary:hover { background: #1e3a1e; }

  .search-hint {
    color: #5a5a7a;
    font-size: 0.72rem;
  }
  .search-hint kbd {
    display: inline-block;
    padding: 0 3px;
    font-family: monospace;
    background: #222;
    border: 1px solid #444;
    border-radius: 3px;
    color: #888;
    font-size: 0.7rem;
  }

  .count { color: #7c7c9a; font-size: 0.82rem; }
  .count.muted { color: #555; }

  /* Search bar fills entire toolbar */
  .search-bar {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex: 1;
  }
  .search-icon { font-size: 0.75rem; opacity: 0.6; }
  .search-input {
    flex: 1;
    padding: 0.3rem 0.4rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.82rem;
    outline: none;
  }
  .search-input:focus { border-color: #6a6a9a; }
  .search-input::placeholder { color: #555; }
  .search-clear {
    background: none;
    border: none;
    color: #7c7c9a;
    cursor: pointer;
    font-size: 0.8rem;
    padding: 0.2rem;
  }
  .search-clear:hover { color: #e0e0e0; }
</style>
