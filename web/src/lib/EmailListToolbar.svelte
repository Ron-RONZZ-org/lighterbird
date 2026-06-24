<script>
  let {
    selectionMode = false,
    numSelected = 0,
    onToggleMode = () => {},
    onDelete = () => {},
    onMove = () => {},
  } = $props();
</script>

<div class="toolbar" class:active={selectionMode || numSelected > 0}>
  <div class="left">
    <button class="tool-btn" title="Toggle selection mode (V)" onclick={onToggleMode}>
      {selectionMode ? "Exit Select" : "Select"}
    </button>
    <span class="hint">
      Press <kbd>v</kbd> to toggle
    </span>
  </div>

  {#if selectionMode}
    <div class="center">
      {#if numSelected > 0}
        <span class="count">{numSelected} selected</span>
      {:else}
        <span class="count muted">Select messages with click or <kbd>Space</kbd></span>
      {/if}
    </div>

    <div class="right">
      <button
        class="tool-btn"
        disabled={numSelected === 0}
        onclick={onMove}
        title="Move selected (Ctrl+M)"
      >Move</button>
      <button
        class="tool-btn danger"
        disabled={numSelected === 0}
        onclick={onDelete}
        title="Delete selected (Delete key)"
      >Delete</button>
    </div>
  {/if}
</div>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    gap: 1rem;
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
    gap: 0.5rem;
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
    font-size: 0.8rem;
    transition: background 0.1s;
  }
  .tool-btn:hover:not(:disabled) {
    background: #3a3a5e;
  }
  .tool-btn:disabled {
    opacity: 0.4;
    cursor: default;
  }
  .tool-btn.danger:hover:not(:disabled) {
    background: #6b2020;
    border-color: #8b3030;
  }

  .hint {
    color: #5a5a7a;
    font-size: 0.72rem;
  }
  .hint kbd {
    display: inline-block;
    padding: 0 3px;
    font-family: monospace;
    background: #222;
    border: 1px solid #444;
    border-radius: 3px;
    color: #888;
    font-size: 0.7rem;
  }

  .count {
    color: #7c7c9a;
    font-size: 0.82rem;
  }
  .count.muted {
    color: #555;
  }
</style>
