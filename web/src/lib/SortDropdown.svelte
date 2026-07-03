<script>
  /**
   * SortDropdown.svelte — Sort order and group-by dropdown panel.
   * Extracted from EmailFolderTree.svelte for use in list tabs.
   */
  let {
    sort = "newest",
    groupByConversation = false,
    groupBySender = false,
    sortOptions = [
      { value: "newest", label: "Newest First" },
      { value: "oldest", label: "Oldest First" },
    ],
    onSortChange = () => {},
    onGroupChange = () => {},
    onGroupBySenderChange = () => {},
  } = $props();
</script>

<div class="sort-dropdown">
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
        checked={groupBySender}
        onchange={(e) => onGroupBySenderChange(e.target.checked)}
      />
      <span>Group by Sender</span>
    </label>
  </div>

  {#if onGroupChange !== undefined}
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
  {/if}
</div>

<style>
  .sort-dropdown {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    font-family: monospace;
    font-size: 0.82rem;
    min-width: 180px;
  }
  .section-title {
    margin: 0 0 0.3rem;
    font-size: 0.72rem;
    color: var(--clr-muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
  }
  .sort-section {
    padding-top: 0.25rem;
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
