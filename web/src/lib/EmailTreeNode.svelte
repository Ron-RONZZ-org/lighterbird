<script>
  /** Recursive tree node for EmailFolderTree.
   *
   * Shared by EmailFolderPanel (folder visibility in email list) and
   * EmailFolderTab (full-screen folder management).
   *
   * Props marked [Tab] are only used by EmailFolderTab; the panel
   * simply omits them.
   */
  import EmailTreeNode from "./EmailTreeNode.svelte";

  let {
    node = {},
    onToggle = () => {},
    onExpand = () => {},
    depth = 0,
    // ── New props ──────────────────────────────────────────────────
    showCheckboxes = false,       // [Panel:true] [Tab:selectionMode]
    activePath = "",              // [Tab only]  Currently active folder path
    onActivate = () => {},        // [Tab only]  Click label to set active
    onContextMenu = () => {},     // [Tab only]  Right-click → (path, event)
    onDoubleClick = () => {},     // [Tab only]  Dbl-click → inline rename
    onDragStart = () => {},       // [Tab only]  DnD source: (path, event)
    onDragOver = () => {},        // [Tab only]  DnD drop zone: (path, event)
    onDrop = () => {},            // [Tab only]  DnD completion: (dragged, target)
  } = $props();

  let paddingLeft = $derived(12 + depth * 16);
  let isActive = $derived(activePath === node.path && !!activePath);
  let isDragOver = $state(false);

  function handleDragStart(e) {
    if (!node.path) return;
    e.dataTransfer.setData("text/plain", node.path);
    e.dataTransfer.effectAllowed = "move";
    onDragStart(node.path, e);
  }

  function handleDragOver(e) {
    if (!node.path || !node.isFolder) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    isDragOver = true;
    onDragOver(node.path, e);
  }

  function handleDragLeave() {
    isDragOver = false;
  }

  function handleDrop(e) {
    e.preventDefault();
    isDragOver = false;
    const draggedPath = e.dataTransfer.getData("text/plain");
    if (draggedPath && node.path) {
      onDrop(draggedPath, node.path);
    }
  }

  function handleClick() {
    if (node.isFolder && onActivate) {
      onActivate(node.path);
    }
  }

  function handleRightClick(e) {
    e.preventDefault();
    e.stopPropagation();
    if (onContextMenu) onContextMenu(node.path, e);
  }

  function handleDblClick(e) {
    e.stopPropagation();
    if (node.isFolder && onDoubleClick) onDoubleClick(node.path);
  }
</script>

<div
  class="tree-node"
  class:active={isActive}
  class:drag-over={isDragOver}
  class:folder-node={node.isFolder}
  style="padding-left: {paddingLeft}px"
  ondragover={handleDragOver}
  ondragleave={handleDragLeave}
  ondrop={handleDrop}
>
  {#if node.children && node.children.length > 0}
    <button
      class="expand-btn"
      onclick={() => onExpand(node.path)}
      aria-label={node.expanded ? "Collapse" : "Expand"}
    >
      {node.expanded ? "\u25BC" : "\u25B6"}
    </button>
  {:else}
    <span class="expand-spacer"></span>
  {/if}

  {#if showCheckboxes}
    {#if node.isFolder}
      <input
        type="checkbox"
        class="folder-check"
        checked={node.visible}
        onchange={() => onToggle(node.path)}
      />
    {:else}
      <span class="check-spacer"></span>
    {/if}
  {:else if node.isFolder && depth === 0}
    <!-- Account-level node — show a subtle indent even without checkbox -->
    <span class="check-spacer"></span>
  {/if}

  <span
    class="node-label"
    class:account={!node.isFolder && (node.children?.length || 0) > 0}
    class:active-label={isActive}
    role="treeitem"
    tabindex="-1"
    onclick={handleClick}
    oncontextmenu={handleRightClick}
    ondblclick={handleDblClick}
    draggable={node.isFolder ? "true" : undefined}
    ondragstart={handleDragStart}
    onkeydown={(e) => {
      if ((e.key === "Enter" || e.key === " ") && node.isFolder) {
        e.preventDefault();
        handleClick();
      }
    }}
  >
    {node.name}
  </span>

  {#if node.expanded && node.children && node.children.length > 0}
    <div class="children">
      {#each node.children as child}
        <EmailTreeNode
          node={child}
          {onToggle}
          {onExpand}
          {depth}
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
    </div>
  {/if}
</div>

<style>
  .tree-node {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.2rem 0.25rem;
    min-height: 1.6rem;
    flex-wrap: wrap;
    border-left: 2px solid transparent;
    transition: background 0.08s, border-color 0.08s;
  }
  .tree-node:hover { background: #2a2a44; }
  .tree-node.active {
    background: #1a2a3e;
    border-left-color: #4a8acc;
  }
  .tree-node.folder-node { cursor: default; }
  .tree-node.drag-over {
    background: #1a3a2e;
    border-left-color: #4acc8a;
  }
  .expand-btn {
    background: none; border: none; color: var(--clr-dim); cursor: pointer;
    font-size: 0.6rem; width: 1rem; text-align: center; flex-shrink: 0; padding: 0;
  }
  .expand-btn:hover { color: #e0e0e0; }
  .expand-spacer { width: 1rem; flex-shrink: 0; }
  .folder-check { width: 0.9rem; height: 0.9rem; accent-color: #4a6fa5; flex-shrink: 0; cursor: pointer; }
  .check-spacer { width: 0.9rem; flex-shrink: 0; }
  .node-label {
    color: #ccc; cursor: pointer; flex: 1; overflow: hidden;
    text-overflow: ellipsis; white-space: nowrap; font-size: 0.8rem;
    user-select: none;
  }
  .node-label.account { color: #e0e0e0; font-weight: 600; font-size: 0.82rem; }
  .node-label.active-label {
    color: #8ab8ff;
    font-weight: 600;
  }
  .node-label[draggable="true"] {
    cursor: grab;
  }
  .node-label[draggable="true"]:active {
    cursor: grabbing;
  }
  .children { width: 100%; }
</style>
