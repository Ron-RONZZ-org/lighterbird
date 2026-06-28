<script>
  /** Recursive tree node for EmailFolderTree. */
  let {
    node = {},
    onToggle = () => {},
    onExpand = () => {},
    depth = 0,
  } = $props();

  let paddingLeft = $derived(12 + depth * 16);
</script>

<div class="tree-node" style="padding-left: {paddingLeft}px">
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

  <span class="node-label" class:account={!node.isFolder && (node.children?.length || 0) > 0}
    role="button" tabindex="-1" onclick={() => { if (node.isFolder) onToggle(node.path); }}>
    {node.name}
  </span>

  {#if node.expanded && node.children && node.children.length > 0}
    <div class="children">
      {#each node.children as child}
        <svelte:self node={child} {onToggle} {onExpand} {depth} />
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
  }
  .tree-node:hover { background: #2a2a44; }
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
  }
  .node-label.account { color: #e0e0e0; font-weight: 600; font-size: 0.82rem; }
  .children { width: 100%; }
</style>
