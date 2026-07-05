<script>
  let { msgUuid = "", attachmentCount = 0 } = $props();

  let attachments = $state([]);
  let isLoading = $state(false);
  let error = $state("");

  $effect(() => {
    if (msgUuid && attachmentCount > 0) {
      fetchAttachments();
    } else {
      attachments = [];
    }
  });

  async function fetchAttachments() {
    if (!msgUuid || attachmentCount === 0) return;
    isLoading = true;
    error = "";
    try {
      const resp = await fetch(`/api/v1/email/messages/${msgUuid}/attachments`);
      if (resp.ok) {
        const data = await resp.json();
        attachments = data.attachments || [];
      } else {
        error = "Failed to load attachments.";
      }
    } catch {
      error = "Network error loading attachments.";
    } finally {
      isLoading = false;
    }
  }

  function downloadAttachment(att) {
    window.open(`/api/v1/email/attachments/${att.uuid}/download`, "_blank");
  }

  function formatFileSize(bytes) {
    if (!bytes) return "";
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  }
</script>

{#if isLoading}
  <div class="attachment-bar">
    <span class="att-loading">Loading attachments…</span>
  </div>
{:else if error}
  <div class="attachment-bar att-error">
    <span>{error}</span>
  </div>
{:else if attachments.length > 0}
  <div class="attachment-bar">
    <span class="att-label">Attachments ({attachments.length})</span>
    {#each attachments as att}
      <button class="att-btn" onclick={() => downloadAttachment(att)} title="Download {att.filename} ({formatFileSize(att.size)})">
        <span class="att-icon">📎</span>
        <span class="att-name">{att.filename}</span>
        <span class="att-size">{formatFileSize(att.size)}</span>
      </button>
    {/each}
  </div>
{/if}

<style>
  .attachment-bar {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.35rem 0.75rem;
    background: #16162a;
    border-bottom: 1px solid #333;
    flex-wrap: wrap;
    flex-shrink: 0;
  }
  .attachment-bar.att-error {
    color: #c44;
    font-size: 0.78rem;
  }
  .att-loading {
    color: var(--clr-muted);
    font-size: 0.78rem;
    font-style: italic;
  }
  .att-label {
    color: var(--clr-sub);
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-right: 0.2rem;
  }
  .att-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.2rem;
    padding: 0.15rem 0.5rem;
    background: #2a2a44;
    border: 1px solid #4a4a6a;
    border-radius: 4px;
    color: #b0b0c0;
    font-family: monospace;
    font-size: 0.75rem;
    cursor: pointer;
    transition: background 0.1s, border-color 0.1s;
    white-space: nowrap;
  }
  .att-btn:hover {
    background: #3a3a5a;
    border-color: #6a6a9a;
    color: #e0e0e0;
  }
  .att-icon { font-size: 0.75rem; }
  .att-name { max-width: 12rem; overflow: hidden; text-overflow: ellipsis; }
  .att-size { color: var(--clr-muted); font-size: 0.68rem; }
</style>
