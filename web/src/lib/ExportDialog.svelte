<script>
  import { tick } from "svelte";
  import { createDialogTrap, sanitizeFilename } from "./listTabShared.svelte.js";

  let {
    domain = "",
    items = [],
    format = "",
    onClose = () => {},
  } = $props();

  let dialogEl;
  let downloadBtn = $state(null);

  let status = $state("");
  let statusMessage = $state("");

  const DOMAIN_CONFIG = {
    email: { type: "download", filename: (item) => sanitizeFilename(item.title || item.uuid, ".eml") },
    calendar: { type: "json", dataKey: "ics", filenameKey: "filename", defaultFilename: "calendar.ics" },
    contacts: { type: "json", dataKey: "vcf", defaultFilename: "contacts.vcf" },
    todo: { type: "text", defaultFilename: "todo.md" },
    journal: { type: "text", defaultFilename: "journal.md" },
    letters: { type: "json", dataKey: "markdown", filenameKey: "filename", defaultFilename: "letter.md" },
  };

  function exportUrl(uuid) {
    if (domain === "contacts") return `/api/v1/contacts/export-vcf?uuid=${uuid}`;
    return `/api/v1/${domain}/export-${format}/${uuid}`;
  }

  async function downloadAll() {
    status = "downloading";
    try {
      for (const item of items) {
        await downloadItem(item);
      }
      status = "done";
      statusMessage = `Exported ${items.length} item(s).`;
    } catch (err) {
      status = "error";
      statusMessage = err.message || "Export failed.";
    }
  }

  async function downloadItem(item) {
    const url = exportUrl(item.uuid);
    const cfg = DOMAIN_CONFIG[domain];
    if (!cfg) throw new Error(`Unknown domain: ${domain}`);

    if (cfg.type === "download") {
      window.open(url, "_blank");
      await new Promise((r) => setTimeout(r, 500));
      return;
    }

    const resp = await fetch(url);
    if (!resp.ok) {
      let msg = `HTTP ${resp.status}`;
      try { const d = await resp.json(); msg = d.detail || d.error || msg; } catch {}
      throw new Error(msg);
    }

    let filename;
    let content;

    if (cfg.type === "json") {
      const data = await resp.json();
      content = data[cfg.dataKey];
      if (!content) throw new Error("Empty export response");
      filename = cfg.filenameKey ? data[cfg.filenameKey] : cfg.defaultFilename;
    } else {
      content = await resp.text();
      if (!content) throw new Error("Empty export response");
      filename = cfg.defaultFilename;
    }

    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const blobUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = filename || cfg.defaultFilename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(blobUrl);
  }

  $effect(() => {
    tick().then(() => downloadBtn?.focus());
  });

  const trapKeydown = createDialogTrap(() => dialogEl, (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      e.stopPropagation();
      onClose();
    }
  });
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<div class="export-overlay" role="alertdialog" aria-modal="true" aria-label="Export"
     onclick={onClose} onkeydown={trapKeydown} bind:this={dialogEl} tabindex="0">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="export-box" onclick={(e) => e.stopPropagation()}>
    <h3 class="export-title">Export {items.length} item(s)</h3>
    <p class="export-info">{domain} &mdash; .{format} format</p>

    {#if items.length > 0}
      <ul class="export-items">
        {#each items as item}
          <li title={item.uuid}>{item.title || item.uuid.slice(0, 8)}</li>
        {/each}
      </ul>
    {/if}

    {#if status === "done"}
      <p class="status-ok">{statusMessage}</p>
    {:else if status === "error"}
      <p class="status-err">{statusMessage}</p>
    {/if}

    <div class="actions">
      {#if status !== "done"}
        <button class="tool-btn primary" onclick={downloadAll}
                disabled={status === "downloading" || items.length === 0}
                bind:this={downloadBtn}>
          {status === "downloading" ? "Downloading…" : "Download"}
        </button>
      {/if}
      <button class="tool-btn" onclick={onClose}>Cancel</button>
    </div>
  </div>
</div>

<style>
  .export-overlay {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100;
  }
  .export-box {
    background: #22223a;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 1.5rem 2rem;
    min-width: 320px;
    max-width: 480px;
    font-family: system-ui, monospace;
  }
  .export-title {
    color: #e0e0e0;
    font-size: 1rem;
    font-weight: 600;
    margin: 0 0 0.25rem;
  }
  .export-info {
    color: #888;
    font-size: 0.8rem;
    margin: 0 0 0.75rem;
  }
  .export-items {
    list-style: none;
    padding: 0;
    margin: 0 0 0.75rem;
    max-height: 200px;
    overflow-y: auto;
  }
  .export-items li {
    color: #c0c0c0;
    font-size: 0.85rem;
    padding: 0.2rem 0;
    border-bottom: 1px solid #2a2a3e;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .export-items li:last-child {
    border-bottom: none;
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
