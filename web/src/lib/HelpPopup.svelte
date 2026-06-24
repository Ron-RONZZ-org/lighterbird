<script>
  let { data = [] } = $props();
</script>

<div class="help">
  {#each data as item}
    <div class="row">
      <span class="cmd">{item.name}</span>
      <span class="desc">{item.description}</span>
    </div>
  {/each}
</div>

<style>
  .help {
    font-family: monospace;
    font-size: 0.85rem;
  }
  .row {
    display: flex;
    gap: 1rem;
    padding: 0.3rem 0;
    border-bottom: 1px solid #2a2a3e;
  }
  .row:last-child {
    border-bottom: none;
  }
  .cmd {
    color: #e0e0e0;
    min-width: 16rem;
    white-space: pre;
  }
  .desc {
    color: var(--clr-sub);
  }
</style>
