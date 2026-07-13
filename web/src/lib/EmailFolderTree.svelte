<script>
  /**
   * EmailFolderTree.svelte — Multi-level folder tree with checkbox visibility
   * toggles, sort options, group-by toggle, and new folder creation.
   *
   * Shared by EmailFolderPanel (email list dropdown) and EmailFolderTab
   * (full-screen folder management). New props marked [Tab] are only used
   * by EmailFolderTab; the panel simply omits them.
   */
  import EmailTreeNode from "./EmailTreeNode.svelte";

  let {
    folders = [],
    folderVisibility = {},
    expandedFolders = [],
    sort = "newest",
    groupByConversation = false,
    groupBySender = false,
    onToggleFolder = () => {},
    onToggleExpand = () => {},
    onSortChange = () => {},
    onGroupChange = () => {},
    onGroupBySenderChange = () => {},
    onCreateFolder = null,
    // ── New props (pass-through to EmailTreeNode) ───────────────────
    showCheckboxes = false,        // [Panel:true] [Tab:selectionMode]
    activePath = "",               // [Tab only]  Active folder path
    onActivate = () => {},         // [Tab only]  Click label to set active
    onContextMenu = () => {},      // [Tab only]  Right-click menu
    onDoubleClick = () => {},      // [Tab only]  Double-click rename
    onDragStart = () => {},        // [Tab only]  DnD source
    onDragOver = () => {},         // [Tab only]  DnD drop zone
    onDrop = () => {},             // [Tab only]  DnD completion
  } = $props();

  let tree = $derived(buildTree(folders));
  let showNewFolderInput = $state(false);
  let newFolderName = $state("");
  let creating = $state(false);
  let createError = $state("");

  function buildTree(flatFolders) {
    const root = {};
    for (const f of flatFolders) {
      const path = f.label || `${f.account_email}/${f.folder_name}`;
      const parts = path.split("/");
      let node = root;
      for (const part of parts) {
        if (!node[part]) node[part] = {};
        node = node[part];
      }
      node._folder = f;
      node._path = path;
    }
    return buildTreeNodes(root, "");
  }

  function buildTreeNodes(obj, prefix) {
    const nodes = [];
    for (const [key, val] of Object.entries(obj)) {
      if (key.startsWith("_")) continue;
      const path = prefix ? `${prefix}/${key}` : key;
      const hasChildren = Object.keys(val).some((k) => !k.startsWith("_"));
      const isFolder = !!val._folder;
      nodes.push({
        name: key,
        path,
        isFolder,
        folder: val._folder || null,
        children: hasChildren ? buildTreeNodes(val, path) : [],
        expanded: expandedFolders.includes(path),
        visible: folderVisibility[path] !== false,
      });
    }
    return nodes;
  }

  function handleToggle(path) {
    onToggleFolder(path);
  }

  function handleExpand(path) {
    onToggleExpand(path);
  }

  async function handleCreateFolder() {
    const name = newFolderName.trim();
    if (!name) return;
    if (!onCreateFolder) return;
    creating = true;
    createError = "";
    try {
      await onCreateFolder(name);
      newFolderName = "";
      showNewFolderInput = false;
    } catch (err) {
      createError = err.message || "Failed to create folder";
    } finally {
      creating = false;
    }
  }
</script>

<div class="folder-tree">
  <div class="tree-section">
    <div class="section-header">
      <h4 class="section-title">Folders</h4>
      {#if onCreateFolder}
        <button class="new-folder-btn" onclick={() => { showNewFolderInput = !showNewFolderInput; newFolderName = ""; createError = ""; }}
                title="Create new folder">+ New</button>
      {/if}
    </div>
    <div class="tree-scroll">
      {#each tree as node}
        <EmailTreeNode
          {node}
          onToggle={handleToggle}
          onExpand={handleExpand}
          depth={0}
          {showCheckboxes}
          {activePath}
          {onActivate}
          {onContextMenu}
          {onDoubleClick}
          {onDragStart}
          {onDragOver}
          {onDrop}
        />
      {/each}
      {#if tree.length === 0}
        <p class="empty-tree">No folders found.</p>
      {/if}
    </div>
    {#if showNewFolderInput}
      <div class="new-folder-form">
        <input
          type="text"
          class="new-folder-input"
          placeholder="Folder name (e.g. My Folder)"
          bind:value={newFolderName}
          onkeydown={(e) => { if (e.key === "Enter") handleCreateFolder(); if (e.key === "Escape") { showNewFolderInput = false; } }}
          disabled={creating}
        />
        <div class="new-folder-actions">
          <button class="tool-btn primary" onclick={handleCreateFolder} disabled={creating || !newFolderName.trim()}>
            {creating ? "Creating…" : "Create"}
          </button>
          <button class="tool-btn" onclick={() => { showNewFolderInput = false; }}>Cancel</button>
        </div>
        {#if createError}
          <p class="new-folder-error">{createError}</p>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .folder-tree {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    font-family: monospace;
    font-size: 0.82rem;
  }
  .section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 0.3rem;
  }
  .section-title {
    margin: 0;
    font-size: 0.72rem;
    color: var(--clr-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
  }
  .new-folder-btn {
    padding: 0.15rem 0.4rem;
    border: 1px solid #3a6a3a;
    border-radius: 3px;
    background: transparent;
    color: #7fdb7f;
    font-family: monospace;
    font-size: 0.72rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .new-folder-btn:hover { background: #1e3a1e; }
  .tree-scroll {
    max-height: 250px;
    overflow-y: auto;
    border: 1px solid #2a2a3e;
    border-radius: 4px;
    padding: 0.25rem 0;
    background: #16162a;
  }
  .empty-tree {
    color: var(--clr-muted);
    text-align: center;
    padding: 1rem;
    font-size: 0.78rem;
  }
  .new-folder-form {
    margin-top: 0.4rem;
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .new-folder-input {
    padding: 0.3rem 0.4rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.8rem;
    outline: none;
  }
  .new-folder-input:focus { border-color: #6a6a9a; }
  .new-folder-actions {
    display: flex;
    gap: 0.3rem;
  }
  .tool-btn {
    padding: 0.2rem 0.5rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #2a2a3e;
    color: #e0e0e0;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.75rem;
    transition: background 0.1s;
  }
  .tool-btn:hover:not(:disabled) { background: #3a3a5e; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .tool-btn.primary { border-color: #3a6a3a; color: #7fdb7f; }
  .tool-btn.primary:hover:not(:disabled) { background: #1e3a1e; }
  .new-folder-error {
    color: #d06;
    font-size: 0.72rem;
    margin: 0;
  }
</style>
