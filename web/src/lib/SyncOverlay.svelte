<script>
  /**
   * SyncOverlay.svelte — Full-page blocking overlay with sync progress.
   *
   * Shows a centered spinner + progress bar during IMAP sync.
   * Used by EmailListTab and EmailFolderTab on mount.
   */
  import ProgressBar from "./ProgressBar.svelte";

  let {
    syncProgress = null,
    title = "Syncing…",
    error = "",
    onCancel = null,
  } = $props();

  let folderName = $derived(syncProgress?.folder_name || "");
  let accountLabel = $derived(syncProgress?.account_email
    ? syncProgress.account_email
    : "");
  let folderStatus = $derived(
    syncProgress?.current_folder != null && syncProgress?.total_folders != null
      ? `Folder ${Math.min(syncProgress.current_folder + 1, syncProgress.total_folders)} of ${syncProgress.total_folders}`
      : ""
  );
  let msgCount = $derived(
    syncProgress?.total != null
      ? `${syncProgress.total} messages`
      : "Preparing…"
  );
</script>

<div class="sync-overlay" role="status" aria-label="Synchronizing">
  <div class="sync-card">
    <div class="sync-spinner">
      <svg class="spinner" viewBox="0 0 24 24" width="32" height="32">
        <circle class="spinner-bg" cx="12" cy="12" r="10" fill="none" stroke="#333" stroke-width="3" />
        <circle class="spinner-arc" cx="12" cy="12" r="10" fill="none" stroke="#7c9bff" stroke-width="3"
          stroke-dasharray="31.4 31.4" stroke-linecap="round" />
      </svg>
    </div>

    <h3 class="sync-title">{title}</h3>

    {#if syncProgress}
      <div class="sync-progress">
        <ProgressBar
          current={syncProgress.current_folder}
          total={syncProgress.total_folders}
          status={syncProgress.status}
          compact={false}
        />
      </div>

      <div class="sync-details">
        {#if folderName}
          <span class="sync-detail">📁 {folderName}</span>
        {/if}
        {#if folderStatus}
          <span class="sync-detail">{folderStatus}</span>
        {/if}
        <span class="sync-detail">{msgCount}</span>
      </div>
    {:else}
      <p class="sync-waiting">Starting sync…</p>
    {/if}

    {#if error}
      <p class="sync-error">{error}</p>
    {/if}

    {#if onCancel}
      <button class="cancel-btn" onclick={onCancel}>Cancel</button>
    {/if}
  </div>
</div>

<style>
  .sync-overlay {
    position: absolute;
    inset: 0;
    background: rgba(10, 10, 20, 0.85);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 300;
    backdrop-filter: blur(2px);
  }

  .sync-card {
    background: #1a1a2e;
    border: 1px solid #3a3a5a;
    border-radius: 12px;
    padding: 2rem 2.5rem;
    text-align: center;
    max-width: 420px;
    width: 90%;
    font-family: monospace;
    color: #e0e0e0;
  }

  .sync-spinner {
    margin-bottom: 1rem;
  }

  .spinner {
    animation: spin 1.2s linear infinite;
  }
  .spinner-bg { opacity: 0.3; }
  .spinner-arc {
    transform-origin: center;
    animation: arc-rotate 1.2s ease-in-out infinite;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }
  @keyframes arc-rotate {
    0% { stroke-dashoffset: 62.8; }
    50% { stroke-dashoffset: 15.7; }
    100% { stroke-dashoffset: 62.8; }
  }

  .sync-title {
    margin: 0 0 1rem;
    font-size: 1.1rem;
    font-weight: 600;
    color: #e0e0e0;
  }

  .sync-progress {
    margin-bottom: 0.75rem;
  }

  .sync-details {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    font-size: 0.82rem;
    color: #7a7a9a;
  }

  .sync-detail {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sync-waiting {
    color: #7a7a9a;
    font-size: 0.85rem;
  }

  .sync-error {
    color: #e07070;
    font-size: 0.82rem;
    margin-top: 0.5rem;
  }

  .cancel-btn {
    margin-top: 1rem;
    padding: 0.4rem 1rem;
    border: 1px solid #555;
    border-radius: 4px;
    background: transparent;
    color: #999;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.82rem;
    transition: background 0.1s, color 0.1s;
  }
  .cancel-btn:hover {
    background: #2a2a44;
    color: #e0e0e0;
  }
</style>
