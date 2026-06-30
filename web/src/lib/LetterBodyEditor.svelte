<script>
  /**
   * Letter body editor — inline textarea with format selection and file upload toggle.
   *
   * Props:
   *   body       — Current body text value (bound)
   *   bodyFormat — Current format: "markdown" | "html" | "text"
   *   bodyPath   — File path when in file-upload mode
   *   onbodychange(body, format) — Called when body or format changes
   *   onbodypathchange(path)     — Called when file path changes
   */
  let {
    body = $bindable(""),
    bodyFormat = $bindable("markdown"),
    bodyPath = $bindable(""),
    onbodychange,
    onbodypathchange,
  } = $props();

  let useFile = $state(false);

  const FORMATS = [
    { value: "markdown", label: "Markdown" },
    { value: "html", label: "HTML" },
    { value: "text", label: "Plain Text" },
  ];

  function toggleMode() {
    useFile = !useFile;
  }

  function handleFormatChange(e) {
    bodyFormat = e.target.value;
    onbodychange?.(body, bodyFormat);
  }

  function handleBodyInput(e) {
    body = e.target.value;
    onbodychange?.(body, bodyFormat);
  }

  function handleFilePathInput(e) {
    bodyPath = e.target.value;
    onbodypathchange?.(bodyPath);
  }

  async function openPreviewInTab() {
    // Send body to backend for rendering, then open in new tab
    try {
      const resp = await fetch("/api/v1/letters/render-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: body, format: bodyFormat }),
      });
      if (resp.ok) {
        const data = await resp.json();
        const html = data.html || "<p>(empty)</p>";
        const win = window.open("", "_blank");
        if (win) {
          win.document.write(
            '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            + '<title>Body Preview</title>'
            + '<style>body{font-family:Georgia,"Times New Roman",serif;padding:2em;line-height:1.6;color:#000;background:#fff;max-width:21cm;margin:0 auto;}</style>'
            + '</head><body>'
            + html
            + '</body></html>'
          );
          win.document.close();
        }
      } else {
        alert("Preview unavailable");
      }
    } catch {
      alert("Preview unavailable");
    }
  }
</script>

<div class="body-editor">
  <div class="editor-header">
    <span class="section-label">Body</span>
    <div class="editor-controls">
      {#if !useFile}
        <select class="format-select" value={bodyFormat} onchange={handleFormatChange}>
          {#each FORMATS as fmt}
            <option value={fmt.value}>{fmt.label}</option>
          {/each}
        </select>
        <button class="tool-btn" onclick={openPreviewInTab}>
          Preview
        </button>
      {/if}
      <button class="tool-btn" onclick={toggleMode}>
        {useFile ? "Write Inline" : "Upload File"}
      </button>
    </div>
  </div>

  {#if useFile}
    <div class="file-upload">
      <input
        type="text"
        class="file-path-input"
        placeholder="Path to .md / .html / .txt file"
        value={bodyPath}
        oninput={handleFilePathInput}
      />
      <span class="hint">Supports .md, .html, .txt — detected automatically</span>
    </div>
  {:else}
    <textarea
      class="body-textarea"
      placeholder="Write your letter body here… Supports Markdown, HTML, or plain text."
      value={body}
      oninput={handleBodyInput}
      rows="12"
    ></textarea>
  {/if}
</div>

<style>
  .body-editor {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }
  .editor-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
  }
  .section-label {
    color: var(--clr-sub);
    font-size: 0.8rem;
    font-weight: 600;
  }
  .editor-controls {
    display: flex;
    gap: 0.4rem;
    align-items: center;
  }
  .format-select {
    padding: 0.25rem 0.4rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.78rem;
    outline: none;
    cursor: pointer;
  }
  .format-select:focus {
    border-color: #6a6a9a;
  }
  .tool-btn {
    padding: 0.25rem 0.5rem;
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
  .body-textarea {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
    line-height: 1.5;
    resize: vertical;
    outline: none;
    box-sizing: border-box;
    min-height: 120px;
  }
  .body-textarea:focus {
    border-color: #6a6a9a;
  }
  .body-textarea::placeholder {
    color: #555;
  }
  .file-upload {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .file-path-input {
    padding: 0.4rem 0.5rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #12122a;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
    outline: none;
  }
  .file-path-input:focus {
    border-color: #6a6a9a;
  }
  .file-path-input::placeholder {
    color: #555;
  }
  .hint {
    font-size: 0.72rem;
    color: var(--clr-muted);
  }
</style>
