<script>
  import { tick } from "svelte";
  import { createDialogTrap } from "./listTabShared.svelte.js";

  let {
    domain = "",
    acceptedFormats = "",
    onImport = () => {},
    onClose = () => {},
    extraData = {},
  } = $props();

  let dialogEl;
  let importBtn = $state(null);

  let serverPath = $state("");
  let status = $state("");
  let statusMessage = $state("");
  let selectedFileName = $state("");

  const IMPORT_CONFIG = {
    email: { endpoint: "/api/v1/email/import-eml" },
    calendar: { endpoint: "/api/v1/calendar/import-ics" },
    contacts: { endpoint: "/api/v1/contacts/import-vcf" },
    todo: { endpoint: "/api/v1/todo/import-md" },
    journal: { endpoint: "/api/v1/journal/import-md" },
    letters: { endpoint: "/api/v1/letters/import-md" },
  };

  async function handleImport() {
    const cfg = IMPORT_CONFIG[domain];
    if (!cfg) {
      status = "error";
      statusMessage = `Unknown domain: ${domain}`;
      return;
    }

    if (!serverPath.trim()) {
      status = "error";
      statusMessage = "Please enter the server path to the file.";
      return;
    }

    status = "importing";
    statusMessage = "";

    try {
      const body = { path: serverPath.trim() };
      if (extraData && Object.keys(extraData).length > 0) {
        Object.assign(body, extraData);
      }

      const resp = await fetch(cfg.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        let errMsg = `HTTP ${resp.status}`;
        try {
          const errData = await resp.json();
          errMsg = errData.detail || errData.error || errMsg;
        } catch {}
        throw new Error(errMsg);
      }

      const result = await resp.json();
      status = "done";
      statusMessage = `Imported ${result.imported || 1} item(s).`;
      onImport(result);
    } catch (err) {
      status = "error";
      statusMessage = err.message || "Import failed.";
    }
  }

  function handleFileSelect(e) {
    const file = e.target?.files?.[0];
    if (file) {
      selectedFileName = file.name;
    }
  }

  $effect(() => {
    tick().then(() => importBtn?.focus());
  });

  const trapKeydown = createDialogTrap(() => dialogEl, (e) => {
    if (e.key === "Enter" && status !== "importing") {
      e.preventDefault();
      e.stopPropagation();
      handleImport();
    } else if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    }
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="import-overlay" role="alertdialog" aria-modal="true" aria-label="Import"
     onclick={onClose} onkeydown={trapKeydown} bind:this={dialogEl} tabindex="0">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="import-box" onclick={(e) => e.stopPropagation()}>
    <h3 class="import-title">Import {domain}</h3>
    <p class="import-info">Select a file and provide the server-side path.</p>

    <div class="field-group">
      <label class="field-label">
        File
        <input type="file" accept={acceptedFormats} onchange={handleFileSelect} class="file-input" />
      </label>
      {#if selectedFileName}
        <span class="file-name">{selectedFileName}</span>
      {/if}
    </div>

    <div class="field-group">
      <label class="field-label">
        Server Path
        <input type="text" class="path-input" placeholder="/path/to/file.{format === '' ? 'ext' : format}"
               bind:value={serverPath} disabled={status === "importing"} />
      </label>
    </div>

    {#if status === "done"}
      <p class="status-ok">{statusMessage}</p>
    {:else if status === "error"}
      <p class="status-err">{statusMessage}</p>
    {/if}

    <div class="actions">
      {#if status !== "done"}
        <button class="tool-btn primary" onclick={handleImport}
                disabled={status === "importing" || !serverPath.trim()}
                bind:this={importBtn}>
          {status === "importing" ? "Importing…" : "Import"}
        </button>
      {/if}
      <button class="tool-btn" onclick={onClose}>Cancel</button>
    </div>
  </div>
</div>

<style>
  .import-overlay {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }
  .import-box {
    background: #22223a;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 1.5rem 2rem;
    min-width: 360px;
    max-width: 500px;
    font-family: system-ui, monospace;
  }
  .import-title {
    color: #e0e0e0;
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 0.25rem;
  }
  .import-info {
    color: #888;
    font-size: 0.8rem;
    margin: 0 0 1rem;
  }
  .field-group {
    margin-bottom: 0.75rem;
  }
  .field-label {
    display: block;
    color: #c0c0c0;
    font-size: 0.82rem;
    margin-bottom: 0.25rem;
  }
  .file-input {
    display: block;
    margin-top: 0.25rem;
    color: #e0e0e0;
    font-size: 0.82rem;
    font-family: monospace;
    width: 100%;
  }
  .file-input::file-selector-button {
    padding: 0.25rem 0.6rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #2a2a3e;
    color: #e0e0e0;
    cursor: pointer;
    font-family: monospace;
    font-size: 0.8rem;
    transition: background 0.1s;
    margin-right: 0.5rem;
  }
  .file-input::file-selector-button:hover {
    background: #3a3a5e;
  }
  .file-name {
    display: inline-block;
    color: #7fdb7f;
    font-size: 0.78rem;
    margin-top: 0.2rem;
  }
  .path-input {
    display: block;
    width: 100%;
    margin-top: 0.25rem;
    padding: 0.35rem 0.5rem;
    background: #1a1a2e;
    border: 1px solid #444;
    border-radius: 4px;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.82rem;
    box-sizing: border-box;
  }
  .path-input:focus {
    outline: none;
    border-color: #5a5a8a;
  }
  .path-input:disabled {
    opacity: 0.5;
  }
  .status-ok {
    color: #7fdb7f;
    font-size: 0.85rem;
    margin: 0 0 0.75rem;
  }
  .status-err {
    color: #d06;
    font-size: 0.85rem;
    margin: 0 0 0.75rem;
  }
  .actions {
    display: flex;
    gap: 0.75rem;
    justify-content: flex-end;
  }
  .tool-btn {
    padding: 0.4rem 1rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: #2a2a3e;
    color: #e0e0e0;
    cursor: pointer;
    font-size: 0.85rem;
    font-family: monospace;
    transition: background 0.1s;
  }
  .tool-btn:hover:not(:disabled) { background: #3a3a5e; }
  .tool-btn:disabled { opacity: 0.4; cursor: default; }
  .tool-btn.primary { border-color: #3a6a3a; color: #7fdb7f; }
  .tool-btn.primary:hover:not(:disabled) { background: #1e3a1e; }
</style>
