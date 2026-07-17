<script>
  /**
   * SyncStatusBar.svelte — Thin non-blocking sync status bar.
   *
   * Shows a compact status line indicating sync state and IDLE health.
   * Never blocks the user — just informs.
   *
   * Props:
   *   statusClass: string — "syncing" | "idle" | "error" | "offline"
   *   summary: string — Human-readable status text
   *   onSync: () => void — Called when the sync button is clicked
   */

  let { statusClass = "idle", summary = "", onSync = () => {} } = $props();
</script>

<button
  class="sync-status-bar status-{statusClass}"
  onclick={onSync}
  title="Click to sync now"
  role="status"
  aria-live="polite"
>
  {#if statusClass === "syncing"}
    <span class="sync-spinner">⟳</span>
  {:else if statusClass === "error"}
    <span class="sync-icon">⚠</span>
  {:else if statusClass === "idle"}
    <span class="sync-icon">✓</span>
  {:else}
    <span class="sync-icon">⟳</span>
  {/if}
  <span class="sync-text">{summary || "Sync"}</span>
</button>

<style>
  .sync-status-bar {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.15rem 0.6rem;
    font-family: monospace;
    font-size: 0.72rem;
    border: none;
    cursor: pointer;
    white-space: nowrap;
    flex-shrink: 0;
    border-radius: 2px;
    transition: background 0.15s;
    line-height: 1.6;
  }
  .sync-status-bar:hover {
    filter: brightness(1.2);
  }

  .status-syncing {
    color: #a0a060;
    background: rgba(160, 160, 96, 0.08);
  }
  .status-syncing:hover {
    background: rgba(160, 160, 96, 0.15);
  }

  .status-idle {
    color: #6aaa6a;
    background: rgba(106, 170, 106, 0.08);
  }
  .status-idle:hover {
    background: rgba(106, 170, 106, 0.15);
  }

  .status-error {
    color: #d07070;
    background: rgba(208, 112, 112, 0.08);
  }
  .status-error:hover {
    background: rgba(208, 112, 112, 0.15);
  }

  .status-offline {
    color: #888;
    background: rgba(136, 136, 136, 0.08);
  }
  .status-offline:hover {
    background: rgba(136, 136, 136, 0.15);
  }

  .sync-spinner {
    display: inline-block;
    animation: syncSpin 1s linear infinite;
  }

  .sync-icon {
    display: inline-block;
  }

  .sync-text {
    white-space: nowrap;
  }

  @keyframes syncSpin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
</style>
