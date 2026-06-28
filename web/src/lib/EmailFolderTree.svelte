<script>
  /**
   * EmailFolderTree.svelte — Multi-level folder tree dropdown with
   * checkbox visibility toggles, sort options, and group-by toggle.
   */
  import EmailTreeNode from "./EmailTreeNode.svelte";

  let {
    folders = [],
    folderVisibility = {},
    expandedFolders = [],
    sort = "newest",
    groupByConversation = false,
    onToggleFolder = () => {},
    onToggleExpand = () => {},
    onSortChange = () => {},
    onGroupChange = () => {},
  } = $props();

  let tree = $derived(buildTree(folders));

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

  let sortOptions = [
    { value: "newest", label: "Newest First" },
    { value: "oldest", label: "Oldest First" },
    { value: "sender", label: "Group by Sender" },
  ];
</script>

<div class="folder-tree">
  <div class="tree-section">
    <h4 class="section-title">Folders</h4>
    <div class="tree-scroll">
      {#each tree as node}
        <EmailTreeNode {node} onToggle={handleToggle} onExpand={handleExpand} depth={0} />
      {/each}
      {#if tree.length === 0}
        <p class="empty-tree">No folders found.</p>
      {/if}
    </div>
  </div>

  <div class="sort-section">
    <h4 class="section-title">Sort</h4>
    <div class="sort-options">
      {#each sortOptions as opt}
        <label class="sort-radio">
          <input
            type="radio"
            name="sort"
            value={opt.value}
            checked={sort === opt.value}
            onchange={() => onSortChange(opt.value)}
          />
          <span>{opt.label}</span>
        </label>
      {/each}
    </div>
  </div>

  <div class="group-section">
    <label class="group-check">
      <input
        type="checkbox"
        checked={groupByConversation}
        onchange={(e) => onGroupChange(e.target.checked)}
      />
      <span>Group by Conversations</span>
    </label>
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
  .section-title {
    margin: 0 0 0.3rem;
    font-size: 0.72rem;
    color: var(--clr-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
  }
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
  .sort-section {
    border-top: 1px solid #2a2a3e;
    padding-top: 0.5rem;
  }
  .sort-options {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .sort-radio {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    cursor: pointer;
    font-size: 0.8rem;
    color: #ccc;
  }
  .sort-radio input { accent-color: #4a6fa5; }
  .group-section {
    border-top: 1px solid #2a2a3e;
    padding-top: 0.5rem;
  }
  .group-check {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    cursor: pointer;
    font-size: 0.8rem;
    color: #ccc;
  }
  .group-check input { width: 0.9rem; height: 0.9rem; accent-color: #4a6fa5; }
</style>
