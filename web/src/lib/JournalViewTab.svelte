<script>
  /** Journal entry detail view — renders title + markdown body, with inline edit support. */

  import { renderMarkdown } from "./markdown.js";
  import { journal as journalApi } from "./api.js";
  import { tabStore } from "./tabStore.svelte.js";
  import { formatListItemDate } from "./listTabShared.svelte.js";

  let { data: _data = {} } = $props();

  let entry = $state({});
  let editing = $state(false);
  let editTitle = $state("");
  let editText = $state("");
  let editDate = $state("");
  let saving = $state(false);

  // Sync from props
  $effect(() => {
    const d = _data;
    if (d && d.uuid) {
      entry = d;
      if (!editing) {
        editTitle = d.title || "";
        editText = d.text || "";
        editDate = d.date || d.created_at?.slice(0, 10) || "";
      }
    }
  });

  function handleKeydown(e) {
    if (e.key === "i" && !e.ctrlKey && !e.metaKey && !e.altKey && !editing) {
      const tag = e.target.tagName;
      if (tag !== "INPUT" && tag !== "TEXTAREA" && !e.target.isContentEditable) {
        e.preventDefault();
        startEdit();
      }
    }
    if (e.key === "Escape" && editing) {
      e.preventDefault();
      cancelEdit();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "p") {
      e.preventDefault();
      window.print();
    }
  }

  function startEdit() {
    editing = true;
    editTitle = entry.title || "";
    editText = entry.text || "";
    editDate = entry.date || entry.created_at?.slice(0, 10) || "";
  }

  function cancelEdit() {
    editing = false;
  }

  async function saveEdit() {
    saving = true;
    try {
      const updates = { title: editTitle, text: editText };
      if (editDate) updates.date = editDate;
      await journalApi.update(entry.uuid, updates);
      const refreshed = await journalApi.get(entry.uuid);
      entry = refreshed;
      editing = false;
    } catch (err) {
      // error handled upstream
    } finally {
      saving = false;
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="journal-view">
  <div class="toolbar">
    <div class="left">
      {#if editing}
        <button class="tool-btn" onclick={cancelEdit}>Cancel</button>
      {:else}
        <button class="tool-btn" onclick={startEdit} title="Edit (i)">✎ Edit <kbd>i</kbd></button>
        <button class="tool-btn" onclick={() => window.print()} title="Print / Export PDF (Ctrl+P)">
          <kbd>Ctrl+P</kbd> Print / PDF
        </button>
      {/if}
    </div>
    <div class="center">
      {#if editing}
        <span class="hint">Editing…</span>
      {/if}
    </div>
    <div class="right">
      {#if editing}
        <button class="tool-btn primary" onclick={saveEdit} disabled={saving || !editTitle}>
          {saving ? "Saving…" : "Save"}
        </button>
      {/if}
    </div>
  </div>

  <div class="content">
    {#if editing}
      <div class="edit-form">
        <div class="field">
          <label for="jv-title">Title</label>
          <input id="jv-title" type="text" bind:value={editTitle} required />
        </div>
        <div class="field">
          <label for="jv-date">Date</label>
          <input id="jv-date" type="date" bind:value={editDate} />
        </div>
        <div class="field">
          <label for="jv-text">Content <span class="field-hint">(markdown)</span></label>
          <textarea id="jv-text" bind:value={editText} rows="12"></textarea>
        </div>
      </div>
    {:else}
      <h1 class="title">{entry.title || "(untitled)"}</h1>

      <div class="meta-row">
        <span class="meta-date">{formatListItemDate(entry.date || entry.created_at)}</span>
        {#if entry.uuid}
          <span class="meta-uuid">{entry.uuid.slice(0, 8)}…</span>
        {/if}
      </div>

      {#if entry.text}
        <div class="rendered">{@html renderMarkdown(entry.text)}</div>
      {:else}
        <p class="empty">No content.</p>
      {/if}
    {/if}
  </div>
</div>

<style>
  .journal-view {
    display: flex;
    flex-direction: column;
    height: 100%;
    position: relative;
  }
  .toolbar {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.3rem 0.5rem; background: #16162a;
    border-bottom: 1px solid #333; min-height: 2.2rem;
    flex-shrink: 0; font-family: monospace; font-size: 0.82rem;
  }
  .left, .right { display: flex; align-items: center; gap: 0.5rem; }
  .center { flex: 1; text-align: center; }
  .tool-btn {
    padding: 0.25rem 0.6rem; border: 1px solid #444; border-radius: 4px;
    background: #2a2a3e; color: #e0e0e0; cursor: pointer;
    font-family: monospace; font-size: 0.8rem; transition: background 0.1s;
  }
  .tool-btn kbd {
    display: inline-block; padding: 0 3px; margin-left: 2px;
    font-family: monospace; font-size: 0.68rem; background: #222;
    border: 1px solid #555; border-radius: 3px; color: #999; line-height: 1.3;
  }
  .tool-btn:hover:not(:disabled) { background: #3a3a5e; }
  .tool-btn.primary { border-color: #3a6a3a; color: #7fdb7f; }
  .tool-btn.primary:hover { background: #1e3a1e; }
  .hint { color: #5a5a7a; font-size: 0.72rem; }
  .content {
    flex: 1;
    overflow-y: auto;
    padding: 1rem 1.5rem;
    font-size: 0.92rem;
    line-height: 1.7;
  }
  .title {
    font-size: 1.4rem;
    font-weight: 700;
    color: #e0e0e0;
    margin: 0 0 0.3rem;
    line-height: 1.3;
  }
  .meta-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 1.2rem;
    flex-wrap: wrap;
  }
  .meta-date {
    color: var(--clr-muted);
    font-size: 0.78rem;
    font-family: monospace;
  }
  .meta-uuid {
    color: #5a5a7a;
    font-size: 0.72rem;
    font-family: monospace;
  }
  .rendered {
    color: #d0d0e0;
    max-width: 100%;
  }
  .rendered :global(p) { margin: 0 0 0.6rem; }
  .rendered :global(p:last-child) { margin-bottom: 0; }
  .rendered :global(pre) {
    background: #111; padding: 0.6rem; border-radius: 6px;
    overflow-x: auto; font-size: 0.82rem; margin: 0.5rem 0;
  }
  .rendered :global(code) {
    background: #111; padding: 1px 4px; border-radius: 3px; font-size: 0.84rem;
  }
  .rendered :global(pre code) { background: none; padding: 0; }
  .rendered :global(a) { color: #8a8acc; text-decoration: underline; }
  .rendered :global(blockquote) {
    border-left: 2px solid #5a5a7a; padding-left: 0.6rem;
    margin: 0.4rem 0; color: #9a9ab0;
  }
  .rendered :global(ul), .rendered :global(ol) { padding-left: 1.2rem; margin: 0.3rem 0; }
  .rendered :global(li) { margin: 0.1rem 0; }
  .rendered :global(h1), .rendered :global(h2), .rendered :global(h3) {
    margin: 0.5rem 0 0.2rem; color: #e0e0e0;
  }
  .rendered :global(hr) { border: none; border-top: 1px solid #333; margin: 0.5rem 0; }
  .rendered :global(table) {
    border-collapse: collapse; margin: 0.5rem 0; font-size: 0.85rem;
  }
  .rendered :global(th), .rendered :global(td) {
    border: 1px solid #333; padding: 0.3rem 0.6rem; text-align: left;
  }
  .rendered :global(th) { background: #1e1e32; color: #b0b0c0; font-weight: 600; }
  .empty {
    color: var(--clr-muted);
    font-style: italic;
    padding: 1rem 0;
  }
  /* Edit form */
  .edit-form { display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label {
    font-size: 0.78rem; color: var(--clr-sub); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em;
  }
  .field-hint {
    font-weight: 400; text-transform: none; letter-spacing: 0;
    color: var(--clr-dim); font-size: 0.7rem;
  }
  .field input, .field textarea {
    background: #16213e; border: 1px solid #333; color: #e0e0e0;
    padding: 0.5rem 0.6rem; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
    outline: none; transition: border-color 0.15s;
  }
  .field input:focus, .field textarea:focus { border-color: #5a5a8a; }
  .field textarea { resize: vertical; min-height: 120px; font-family: inherit; line-height: 1.5; }

  /* Print styles — hide non-essential UI */
  @media print {
    :global(.tab-bar),
    :global(.command-bar),
    :global(.home-content),
    :global(.top-progress),
    .toolbar {
      display: none !important;
    }
    .journal-view {
      padding: 0 !important;
    }
    .content {
      color: #000 !important;
    }
    .rendered :global(a) {
      color: #0000ee !important;
    }
  }
</style>
