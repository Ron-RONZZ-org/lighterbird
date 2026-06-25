<script>
  /**
   * Backup strategy list with Add/Modify/Remove/Test buttons.
   *
   * Props:
   *   items     — array of strategy objects from config
   *   onAdd     — open the add form
   *   onModify  — open the edit form for a strategy
   *   onRemove  — remove a strategy
   *   onTest    — test a strategy's target
   *   testing   — set of strategy ids currently being tested
   *   testResults — map from strategy id to result message
   */

  let { items = [], onAdd = () => {}, onModify = () => {}, onRemove = () => {}, onTest = () => {}, testing = new Set(), testResults = {} } = $props();
</script>

<div class="strategy-list">
  <div class="header">
    <h3 class="title">Backup Strategies</h3>
    <button class="btn-add" onclick={onAdd}>+ Add Strategy</button>
  </div>

  {#if items.length === 0}
    <div class="empty-state">
      <p class="empty-msg">No backup strategies configured.</p>
      <div class="hints">
        <code class="hint-cmd">!backup config add --id daily --label "Daily backups"</code>
        <code class="hint-cmd">!backup config add --id hourly --label "Hourly snapshots" --schedule hourly --max-copies 5</code>
      </div>
    </div>
  {:else}
    <div class="list">
      {#each items as item}
        <div class="row">
          <div class="row-info">
            <span class="row-main">
              {#if item.enabled}
                <span class="enabled-dot" title="Enabled">●</span>
              {:else}
                <span class="disabled-dot" title="Disabled">○</span>
              {/if}
              {item.label || item.id}
            </span>
            <span class="row-sub">{item.id} · {item.schedule} · max {item.max_copies} copies</span>
            <span class="row-meta">target: {item.target}</span>
          </div>
          <div class="row-actions">
            <button
              class="btn-test"
              onclick={() => onTest(item)}
              disabled={testing.has(item.id)}
              title="Test if target is writable"
            >
              {testing.has(item.id) ? "Testing…" : "Test"}
            </button>
            <button class="btn-modify" onclick={() => onModify(item)} title="Modify">Modify</button>
            <button class="btn-remove" onclick={() => onRemove(item)} title="Remove">Remove</button>
          </div>
          {#if testResults[item.id]}
            <div class="test-result" class:test-pass={testResults[item.id].success} class:test-fail={!testResults[item.id].success}>
              {testResults[item.id].message}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .strategy-list {
    font-family: monospace;
    font-size: 0.85rem;
  }
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.75rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid #2a2a3e;
  }
  .title {
    font-size: 0.95rem;
    color: #e0e0e0;
    font-weight: 600;
  }
  .btn-add {
    background: #2a4a2a;
    color: #b0d0b0;
    border: 1px solid #3a6a3a;
    border-radius: 6px;
    padding: 0.35rem 0.75rem;
    font-family: monospace;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-add:hover {
    background: #3a6a3a;
  }
  .empty-state {
    text-align: center;
    padding: 2rem 0;
  }
  .empty-msg {
    color: var(--clr-sub);
    margin-bottom: 1rem;
  }
  .hints {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
    align-items: center;
  }
  .hint-cmd {
    display: inline-block;
    background: #2a2a3e;
    padding: 0.3rem 0.6rem;
    border-radius: 4px;
    color: var(--clr-sub);
    font-size: 0.78rem;
    border: 1px solid #333;
  }
  .list {
    display: flex;
    flex-direction: column;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0.4rem;
    border-bottom: 1px solid #2a2a3e;
    transition: background 0.1s;
  }
  .row:last-child {
    border-bottom: none;
  }
  .row:hover {
    background: #22223a;
  }
  .row-info {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    min-width: 0;
    flex: 1;
  }
  .row-main {
    color: #e0e0e0;
    font-size: 0.85rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .enabled-dot {
    color: #60b080;
    margin-right: 0.3rem;
  }
  .disabled-dot {
    color: #7c7c9a;
    margin-right: 0.3rem;
  }
  .row-sub {
    color: var(--clr-sub);
    font-size: 0.75rem;
  }
  .row-meta {
    color: var(--clr-muted);
    font-size: 0.7rem;
  }
  .row-actions {
    display: flex;
    gap: 0.4rem;
    flex-shrink: 0;
    margin-left: 1rem;
  }
  .btn-test, .btn-modify, .btn-remove {
    padding: 0.25rem 0.55rem;
    border-radius: 4px;
    border: 1px solid #444;
    font-family: monospace;
    font-size: 0.75rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-test {
    background: #2a3a2a;
    color: #b0d0b0;
    border-color: #3a5a3a;
  }
  .btn-test:hover {
    background: #3a5a3a;
  }
  .btn-test:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .btn-modify {
    background: #2a3a5a;
    color: #b0c0d0;
    border-color: #3a5a7a;
  }
  .btn-modify:hover {
    background: #3a5a7a;
  }
  .btn-remove {
    background: #4a2a2a;
    color: #d0a0a0;
    border-color: #6a3a3a;
  }
  .btn-remove:hover {
    background: #6a3a3a;
  }
  .test-result {
    width: 100%;
    font-size: 0.72rem;
    padding: 0.2rem 0.4rem;
    margin-top: 0.2rem;
    border-radius: 4px;
  }
  .test-pass {
    color: #60b080;
    background: #1a2a1a;
  }
  .test-fail {
    color: #d0a0a0;
    background: #2a1a1a;
  }
</style>
