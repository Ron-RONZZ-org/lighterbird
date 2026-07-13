<script>
  /**
   * FolderContextMenu.svelte — Right-click context menu for folder tree nodes.
   *
   * Positioned at cursor / the triggering element. Closes on click-outside
   * or Esc.
   */
  import { createDialogTrap } from "./listTabShared.svelte.js";

  let {
    x = 0,
    y = 0,
    folderPath = "",
    onRename = () => {},
    onDelete = () => {},
    onClose = () => {},
  } = $props();

  let overlay;
  let menu;

  $effect(() => {
    if (menu) menu.focus();
  });

  function trapKeydown(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    }
  }

  function handleOverlayClick(e) {
    if (e.target === overlay || e.target === overlay.querySelector(".context-backdrop")) {
      onClose();
    }
  }
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div
  class="context-backdrop"
  role="presentation"
  onclick={handleOverlayClick}
  onkeydown={trapKeydown}
  bind:this={overlay}
>
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="context-menu"
    role="menu"
    aria-label="Folder actions"
    style="left: {x}px; top: {y}px;"
    bind:this={menu}
    tabindex="0"
    onkeydown={trapKeydown}
  >
    <div class="menu-header">{folderPath}</div>
    <button class="menu-item" role="menuitem" onclick={() => { onRename(folderPath); onClose(); }}>
      ✏️ Rename
    </button>
    <button class="menu-item danger" role="menuitem" onclick={() => { onDelete(folderPath); onClose(); }}>
      🗑️ Delete
    </button>
  </div>
</div>

<style>
  .context-backdrop {
    position: fixed;
    inset: 0;
    z-index: 500;
    background: transparent;
  }

  .context-menu {
    position: fixed;
    background: #1e1e32;
    border: 1px solid #444;
    border-radius: 6px;
    min-width: 160px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.5);
    font-family: monospace;
    font-size: 0.82rem;
    z-index: 501;
    overflow: hidden;
    outline: none;
  }

  .menu-header {
    padding: 0.4rem 0.6rem;
    color: #7a7a9a;
    font-size: 0.72rem;
    border-bottom: 1px solid #333;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 240px;
  }

  .menu-item {
    display: block;
    width: 100%;
    padding: 0.45rem 0.6rem;
    border: none;
    background: transparent;
    color: #e0e0e0;
    cursor: pointer;
    text-align: left;
    font-family: monospace;
    font-size: 0.82rem;
    transition: background 0.08s;
  }

  .menu-item:hover { background: #2a2a50; }
  .menu-item.danger:hover { background: #3a1a1a; color: #e07070; }
</style>
