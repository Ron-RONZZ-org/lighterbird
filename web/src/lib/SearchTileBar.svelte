<script>
  /**
   * SearchTileBar.svelte
   *
   * Displays active search conditions as removable tiles below the navbar.
   * Each tile shows the field name and value, with an [x] to remove it.
   * When all tiles are removed, the bar collapses.
   */
  let {
    filters = {},
    onRemove = () => {},
    onClear = () => {},
  } = $props();

  // Convert filters to display tiles
  let tiles = $derived.by(() => {
    const result = [];
    for (const [key, val] of Object.entries(filters)) {
      if (!val) continue;
      let label = key;
      let displayVal = String(val);
      // Human-friendly labels
      const labels = {
        query: "Text", from: "From", sender: "From", subject: "Subject",
        to: "To", cc: "CC", bcc: "BCC", participant: "Participant",
        priority: "Priority", after: "After", before: "Before",
        folder: "Folder", body: "Body search", header: "Headers only",
        header_text: "Header", body_text: "Body",
        date_from: "From date", date_to: "To date",
      };
      label = labels[key] || key;
      // Truncate long values
      if (displayVal.length > 30) displayVal = displayVal.slice(0, 27) + "…";
      // Boolean filters
      if (val === true || val === "true") displayVal = "on";
      result.push({ key, label, displayVal });
    }
    return result;
  });

  function handleRemove(key) {
    onRemove(key);
  }
</script>

{#if tiles.length > 0}
  <div class="tile-bar">
    <div class="tiles">
      {#each tiles as tile (tile.key)}
        <span class="tile">
          <span class="tile-label">{tile.label}</span>
          <span class="tile-value">{tile.displayVal}</span>
          <button class="tile-x" onclick={() => handleRemove(tile.key)}
                  aria-label="Remove {tile.label} filter">✕</button>
        </span>
      {/each}
    </div>
    <button class="clear-btn" onclick={onClear} title="Clear all filters">Clear all</button>
  </div>
{/if}

<style>
  .tile-bar {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0.75rem;
    background: #1e1e32;
    border-bottom: 1px solid #333;
    flex-wrap: wrap;
    font-family: monospace;
    font-size: 0.78rem;
  }
  .tiles {
    display: flex;
    gap: 0.35rem;
    flex-wrap: wrap;
    flex: 1;
  }
  .tile {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    background: #2a2a50;
    border: 1px solid #4a4a7a;
    border-radius: 4px;
    padding: 0.15rem 0.4rem;
    color: #c0c0e0;
  }
  .tile-label {
    color: #7c7c9a;
    font-size: 0.7rem;
    text-transform: uppercase;
  }
  .tile-value {
    color: #e0e0ff;
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .tile-x {
    background: none;
    border: none;
    color: #7c7c9a;
    cursor: pointer;
    padding: 0;
    font-size: 0.75rem;
    line-height: 1;
    transition: color 0.1s;
  }
  .tile-x:hover { color: #f06060; }
  .clear-btn {
    background: none;
    border: 1px solid #444;
    border-radius: 3px;
    color: #7c7c9a;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.72rem;
    padding: 0.15rem 0.4rem;
    white-space: nowrap;
    flex-shrink: 0;
    transition: color 0.1s, border-color 0.1s;
  }
  .clear-btn:hover { color: #f06060; border-color: #a04040; }
</style>
