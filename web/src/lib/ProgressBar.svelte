<script>
  /**
   * ProgressBar.svelte — A compact progress bar for operation feedback.
   *
   * Props:
   *   current  — Current progress value (0-based index of completed items)
   *   total    — Total items to process
   *   label    — Optional text label shown beside the bar
   *   status   — Optional status string ("running", "complete", "error")
   *   compact  — If true, render inline without margin/padding
   */
  let {
    current = 0,
    total = 1,
    label = "",
    status = "running",
    compact = false,
  } = $props();

  let pct = $derived(
    total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0
  );

  let barColor = $derived(
    status === "error" ? "var(--clr-danger, #d9534f)" :
    status === "complete" ? "var(--clr-success, #5cb85c)" :
    "var(--clr-primary, #7c9bff)"
  );
</script>

<div class="progress-bar-wrapper" class:compact>
  {#if label}
    <span class="progress-label">{label}</span>
  {/if}
  <div class="progress-bar-track" role="progressbar" aria-valuenow={pct}
       aria-valuemin={0} aria-valuemax={100}>
    <div class="progress-bar-fill" style="width: {pct}%; background: {barColor};"></div>
  </div>
  <span class="progress-text">{pct}%</span>
</div>

<style>
  .progress-bar-wrapper {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0.5rem;
    font-family: monospace;
    font-size: 0.78rem;
    color: #c0c0d0;
  }
  .progress-bar-wrapper.compact {
    padding: 0;
    gap: 0.3rem;
  }
  .progress-label {
    white-space: nowrap;
    min-width: 3rem;
  }
  .progress-bar-track {
    flex: 1;
    height: 8px;
    background: #2a2a3e;
    border-radius: 4px;
    overflow: hidden;
    min-width: 60px;
  }
  .progress-bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.3s ease;
  }
  .progress-text {
    white-space: nowrap;
    min-width: 2.5rem;
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
</style>
