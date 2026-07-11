<script>
  import DropdownPanel from "./DropdownPanel.svelte";
  import EmailFolderTree from "./EmailFolderTree.svelte";

  /**
   * EmailFolderPanel.svelte
   *
   * Dropdown panel wrapping EmailFolderTree with folder search, backdrop,
   * and toggle/expand logic.  Folder state is shared with the parent via
   * $bindable so changes are automatically synced.
   *
   * Props:
   *   folderTree       — array of folder objects
   *   selectedFolder   — (bindable) currently selected folder path
   *   messages         — message list (for context)
   *   folderVisibility — (bindable) { path → boolean }
   *   expandedFolders  — (bindable) array of expanded paths
   *   show             — (bindable) visibility of the panel
   *   onRefresh        — callback after folder toggle
   *   onSelectFolder   — callback when a folder is selected
   *   onCreateFolder   — async callback to create a new folder
   *   onClose          — callback to close the panel
   */
  let {
    folderTree = [],
    selectedFolder = $bindable(""),
    messages = [],
    folderVisibility = $bindable({}),
    expandedFolders = $bindable([]),
    show = $bindable(false),
    onRefresh = async () => {},
    onSelectFolder = () => {},
    onCreateFolder = null,
    onClose = () => {},
  } = $props();

  // ── Folder search ───────────────────────────────────────────────────
  let folderSearch = $state("");
  let filteredFolders = $derived(
    folderSearch
      ? folderTree.filter((f) => {
          const name = f.label || f.folder_name || "";
          return name.toLowerCase().includes(folderSearch.toLowerCase());
        })
      : folderTree,
  );

  // ── Handlers ─────────────────────────────────────────────────────────
  function handleToggleFolder(path) {
    const next = { ...folderVisibility };
    next[path] = !(next[path] !== false);
    folderVisibility = next;
    selectedFolder = path;
    onSelectFolder(path);
    onRefresh();
  }

  function handleToggleExpand(path) {
    expandedFolders = expandedFolders.includes(path)
      ? expandedFolders.filter((p) => p !== path)
      : [...expandedFolders, path];
  }

  function handleSelectAll() {
    const next = { ...folderVisibility };
    for (const f of folderTree) {
      const path = f.label || `${f.account_email}/${f.folder_name}`;
      next[path] = true;
    }
    folderVisibility = next;
    onRefresh();
  }

  function handleDeselectAll() {
    const next = { ...folderVisibility };
    for (const f of folderTree) {
      const path = f.label || `${f.account_email}/${f.folder_name}`;
      next[path] = false;
    }
    folderVisibility = next;
    onRefresh();
  }

  function _isTrashName(f) {
    const name = f.folder_name || "";
    return name.toLowerCase() === "trash";
  }

  function handleSelectAllButTrash() {
    const next = { ...folderVisibility };
    for (const f of folderTree) {
      const path = f.label || `${f.account_email}/${f.folder_name}`;
      next[path] = !_isTrashName(f);
    }
    folderVisibility = next;
    onRefresh();
  }
</script>

<DropdownPanel {show} {onClose}>
  <div class="folder-panel">
    <div class="folder-search">
      <input
        type="text"
        class="folder-search-input"
        placeholder="Search folders…"
        bind:value={folderSearch}
        onkeydown={(e) => e.stopPropagation()}
      />
    </div>
    <div class="folder-actions">
      <button class="folder-action-btn" onclick={handleSelectAll} title="Show all folders">All</button>
      <button class="folder-action-btn" onclick={handleSelectAllButTrash} title="Show all folders except Trash">No Trash</button>
      <button class="folder-action-btn" onclick={handleDeselectAll} title="Hide all folders">None</button>
    </div>
    <EmailFolderTree
      folders={filteredFolders}
      {folderVisibility}
      {expandedFolders}
      onToggleFolder={handleToggleFolder}
      onToggleExpand={handleToggleExpand}
      {onCreateFolder}
    />
  </div>
</DropdownPanel>

<style>
  .folder-panel {
    width: 320px;
    padding: 0.75rem;
  }
  .folder-search {
    margin-bottom: 0.5rem;
  }
  .folder-search-input {
    width: 100%;
    padding: 0.35rem 0.5rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.78rem;
    outline: none;
    box-sizing: border-box;
  }
  .folder-search-input:focus {
    border-color: #6a6a9a;
  }
  .folder-search-input::placeholder {
    color: #555;
  }
  .folder-actions {
    display: flex;
    gap: 0.3rem;
    margin-bottom: 0.4rem;
  }
  .folder-action-btn {
    padding: 0.15rem 0.5rem;
    border: 1px solid #444;
    border-radius: 3px;
    background: transparent;
    color: var(--clr-muted, #888);
    font-family: monospace;
    font-size: 0.72rem;
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
  }
  .folder-action-btn:hover {
    background: #2a2a44;
    color: #e0e0e0;
  }
</style>
