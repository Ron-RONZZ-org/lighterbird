<script>
  /** Journal entry write form — used when !journal write is typed interactively. */

  import { drafts as draftsApi } from "./api.js";
  import { createCowrite, CowriteButton, CowritePanel } from "./cowrite/index.js";
  import PreviewDialog from "./PreviewDialog.svelte";
  import { createPreviewState } from "./preview.svelte.js";

  let { initialData = {}, onsubmit, onDirtyChange = () => {} } = $props();
  // svelte-ignore state_referenced_locally
  const _initial = initialData;

  let title = $state(_initial.title || "");
  let text = $state(_initial.text || "");
  let bodyFormat = $state("markdown");
  let date = $state(_initial.date || new Date().toISOString().slice(0, 10));
  let writing = $state(false);
  let savingDraft = $state(false);
  let draftSaved = $state(false);
  let draftUuid = $state(_initial._draft_uuid || null);

  // ── Preview state ─────────────────────────────────────────────────
  let preview = $state(createPreviewState());

  // ── LLM co-writing ─────────────────────────────────────────────────
  let cowrite = $state(createCowrite({
    formType: "journal-write",
    getCurrentContent: () => ({ title, text }),
    applyEdit: (field, t) => {
      if (field === "title") title = t;
      else if (field === "text") text = t;
    },
  }));

  /** Save draft on Ctrl+S */
  async function saveDraft() {
    if (savingDraft) return;
    savingDraft = true;
    draftSaved = false;
    try {
      const result = await draftsApi.save(
        "journal",
        title || "(untitled)",
        { title, text, date },
        draftUuid,
      );
      draftUuid = result.uuid;
      draftSaved = true;
      setTimeout(() => { draftSaved = false; }, 2000);
    } catch { /* silent */ }
    finally { savingDraft = false; }
  }

  function handleFormKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      saveDraft();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit(e);
    }
    // Ctrl+Shift+P — preview content
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "p" || e.key === "P")) {
      e.preventDefault();
      preview.show(text, bodyFormat, "Journal Preview");
    }
  }

  // Dirty state — compare current against initial
  let dirty = $derived(
    title !== (_initial.title || "")
    || text !== (_initial.text || "")
    || date !== (_initial.date || new Date().toISOString().slice(0, 10))
  );
  $effect(() => { onDirtyChange(dirty); });

  async function handleSubmit(e) {
    e.preventDefault();
    if (!title) return;
    writing = true;
    try {
      await onsubmit({
        tokens: ["journal", "write"],
        flags: { date },
        remaining: [title, text],
      });
      onDirtyChange(false);
    } finally {
      writing = false;
    }
  }
</script>

<form onsubmit={handleSubmit} class="journal-write-form">
  <!-- Toolbar -->
  <div class="form-toolbar">
    <div class="toolbar-left">
      <span class="toolbar-title">Write Journal Entry</span>
    </div>
    <div class="toolbar-right">
      <CowriteButton {cowrite} />
    </div>
  </div>

  <div class="field">
    <label for="title">Title</label>
    <input id="title" type="text" bind:value={title} required placeholder="Entry title" />
  </div>
  <div class="field">
    <label for="date">Date</label>
    <input id="date" type="date" bind:value={date} />
  </div>
  <div class="field">
    <div class="field-header">
      <label for="text">Content</label>
      <div class="field-controls">
        <select class="format-select" bind:value={bodyFormat}>
          <option value="markdown">Markdown</option>
          <option value="html">HTML</option>
          <option value="plain">Plain Text</option>
        </select>
        <button type="button" class="preview-btn" onclick={() => preview.show(text, bodyFormat, "Journal Preview")}
          disabled={!text.trim()} title="Preview (Ctrl+Shift+P)">
          Preview <kbd>Ctrl+Shift+P</kbd>
        </button>
      </div>
    </div>
    <textarea id="text" bind:value={text} rows="12" placeholder="Write your journal entry here..."></textarea>
  </div>
  <div class="actions">
    <button type="button" class="draft-btn" onclick={saveDraft} disabled={savingDraft || !title && !text}>
      {#if savingDraft}
        Saving…
      {:else if draftSaved}
        Draft saved ✓
      {:else}
        Save Draft <kbd>Ctrl+S</kbd>
      {/if}
    </button>
    <button type="submit" disabled={writing || !title}>
      {writing ? "Saving..." : "Save Entry"} <kbd>Ctrl+Enter</kbd>
    </button>
  </div>

  {#if cowrite.isActive}
    <CowritePanel {cowrite} />
  {/if}

  {#if preview.showing}
    <PreviewDialog
      showing={preview.showing}
      htmlContent={preview.htmlContent}
      title={preview.title}
      onclose={() => preview.close()}
    />
  {/if}
</form>

<svelte:window onkeydown={handleFormKeydown} />

<style>
  .journal-write-form { padding: 1rem 1rem 0 1rem; display: flex; flex-direction: column; gap: 0.75rem; position: relative; }
  .form-toolbar {
    display: flex; align-items: center; gap: 0.5rem;
    margin: -1rem -1rem 0 -1rem; padding: 0.4rem 0.5rem;
    background: #16162a; border-bottom: 1px solid #333; min-height: 2.2rem;
    flex-shrink: 0; font-family: monospace; font-size: 0.82rem;
  }
  .toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 0.5rem; }
  .toolbar-right { margin-left: auto; }
  .toolbar-title { color: #b0b0c0; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label { font-size: 0.8rem; color: #7c7c9a; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .field-header {
    display: flex; align-items: center; justify-content: space-between;
  }
  .field-controls {
    display: flex; gap: 0.4rem; align-items: center;
  }
  .format-select {
    padding: 0.25rem 0.4rem; border: 1px solid #444; border-radius: 4px;
    background: #12122a; color: #e0e0e0; font-family: monospace;
    font-size: 0.78rem; outline: none; cursor: pointer;
  }
  .format-select:focus { border-color: #6a6a9a; }
  .preview-btn {
    padding: 0.25rem 0.5rem; border: 1px solid #444; border-radius: 4px;
    background: transparent; color: #b0b0c0; font-family: monospace;
    font-size: 0.72rem; cursor: pointer; transition: background 0.1s, color 0.1s;
    white-space: nowrap;
  }
  .preview-btn:hover:not(:disabled) { background: #2a2a44; color: #e0e0e0; }
  .preview-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .field input, .field textarea {
    background: #16213e; border: 1px solid #333; color: #e0e0e0;
    padding: 0.5rem; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
  }
  .field textarea { resize: vertical; min-height: 200px; font-family: inherit; line-height: 1.5; }
  .actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
  .actions button {
    background: #0f3460; color: #e0e0e0; border: none; padding: 0.5rem 1.5rem;
    border-radius: 4px; cursor: pointer; font-size: 0.9rem;
  }
  .actions button:disabled { opacity: 0.5; cursor: not-allowed; }
  .actions button:hover:not(:disabled) { background: #1a4a7a; }
  .draft-btn {
    background: #2a2a3e;
    border: 1px solid #444;
    color: #ccc;
    margin-right: auto;
  }
  .draft-btn:hover:not(:disabled) { background: #3a3a5a; }
  .draft-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .draft-btn kbd {
    display: inline-block;
    padding: 1px 4px;
    background: #222;
    border: 1px solid #555;
    border-radius: 3px;
    font-size: 0.7rem;
    margin-left: 0.2rem;
  }
</style>
