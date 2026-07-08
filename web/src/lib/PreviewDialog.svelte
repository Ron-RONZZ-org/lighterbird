<script>
  /**
   * PreviewDialog.svelte — reusable modal for rendering HTML content preview.
   *
   * Props:
   *   showing     — Whether the dialog is visible
   *   htmlContent — The rendered HTML string to display
   *   title       — Dialog title (default: "Preview")
   *   onclose     — Called when the user closes the dialog
   */
  let {
    showing = false,
    htmlContent = "",
    title = "Preview",
    onclose = () => {},
  } = $props();

  function close() {
    onclose();
  }

  /** Close only when clicking the overlay background, not its children. */
  function handleOverlayClick(e) {
    if (e.target === e.currentTarget) close();
  }

  function handleKeydown(e) {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  }

  /** Open rendered content in a new browser tab */
  function openInTab() {
    if (!htmlContent) return;
    const win = window.open("", "_blank");
    if (win) {
      win.document.write(
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        + '<title>' + title + '</title>'
        + '<style>body{font-family:Georgia,"Times New Roman",serif;padding:2em;line-height:1.6;color:#000;background:#fff;max-width:21cm;margin:0 auto;}img{max-width:100%;}pre{background:#f5f5f5;padding:1em;overflow-x:auto;}</style>'
        + '</head><body>'
        + htmlContent
        + '</body></html>'
      );
      win.document.close();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if showing}
  <!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
  <div class="preview-overlay" onclick={handleOverlayClick} role="dialog" aria-label={title} tabindex="-1">
    <div class="preview-modal" role="document">
      <div class="preview-header">
        <span class="preview-title">{title}</span>
        <div class="preview-actions">
          <button class="tool-btn" onclick={openInTab} title="Open in new tab">
            Open in Tab
          </button>
          <button class="close-btn" onclick={close} aria-label="Close preview" title="Close (Esc)">
            ✕
          </button>
        </div>
      </div>
      <div class="preview-body">
        {#if htmlContent}
          <div class="rendered-content">{@html htmlContent}</div>
        {:else}
          <p class="empty">(empty)</p>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .preview-overlay {
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .preview-modal {
    background: #1a1a2e;
    border: 1px solid #444;
    border-radius: 8px;
    width: 90%;
    max-width: 900px;
    max-height: 85vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5);
  }
  .preview-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 1rem;
    border-bottom: 1px solid #333;
    flex-shrink: 0;
  }
  .preview-title {
    font-family: monospace;
    font-size: 0.85rem;
    color: #b0b0c0;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .preview-actions {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  .tool-btn {
    padding: 0.3rem 0.6rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: transparent;
    color: #b0b0c0;
    font-family: monospace;
    font-size: 0.72rem;
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
    white-space: nowrap;
  }
  .tool-btn:hover {
    background: #2a2a44;
    color: #e0e0e0;
  }
  .close-btn {
    background: none;
    border: none;
    color: #8a4a4a;
    font-size: 1.1rem;
    cursor: pointer;
    padding: 0.1rem 0.4rem;
    line-height: 1;
  }
  .close-btn:hover {
    color: #cc6a6a;
  }
  .preview-body {
    padding: 1.5rem;
    overflow-y: auto;
    flex: 1;
    color: #e0e0e0;
    font-family: Georgia, "Times New Roman", serif;
    font-size: 0.9rem;
    line-height: 1.6;
  }
  .preview-body :global(img) {
    max-width: 100%;
  }
  .preview-body :global(pre) {
    background: #12122a;
    padding: 1rem;
    overflow-x: auto;
    border-radius: 4px;
    font-family: monospace;
    font-size: 0.82rem;
  }
  .preview-body :global(code) {
    background: #12122a;
    padding: 0.15em 0.3em;
    border-radius: 3px;
    font-family: monospace;
    font-size: 0.85em;
  }
  .preview-body :global(pre code) {
    background: none;
    padding: 0;
  }
  .preview-body :global(table) {
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
  }
  .preview-body :global(td), .preview-body :global(th) {
    border: 1px solid #444;
    padding: 0.4em;
  }
  .preview-body :global(th) {
    background: #12122a;
  }
  .preview-body :global(blockquote) {
    border-left: 3px solid #555;
    margin-left: 0;
    padding-left: 1em;
    color: #999;
  }
  .empty {
    color: #707080;
    font-style: italic;
    font-family: monospace;
    font-size: 0.82rem;
  }
</style>
