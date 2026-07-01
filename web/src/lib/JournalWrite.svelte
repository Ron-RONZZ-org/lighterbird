<script>
  /** Journal entry write form — used when !journal write is typed interactively. */

  import { drafts as draftsApi } from "./api.js";
  import { createCowrite, CowriteButton, CowritePanel } from "./cowrite/index.js";

  let { initialData = {}, onsubmit, onDirtyChange = () => {} } = $props();
  // svelte-ignore state_referenced_locally
  const _initial = initialData;

  let title = $state(_initial.title || "");
  let text = $state(_initial.text || "");
  let date = $state(_initial.date || new Date().toISOString().slice(0, 10));
  let writing = $state(false);
  let savingDraft = $state(false);
  let draftSaved = $state(false);
  let draftUuid = $state(_initial._draft_uuid || null);

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
  <div class="field">
    <label for="title">Title</label>
    <input id="title" type="text" bind:value={title} required placeholder="Entry title" />
  </div>
  <div class="field">
    <label for="date">Date</label>
    <input id="date" type="date" bind:value={date} />
  </div>
  <div class="field">
    <label for="text">Content</label>
    <div class="textarea-actions">
      <textarea id="text" bind:value={text} rows="12" placeholder="Write your journal entry here..."></textarea>
      <CowriteButton {cowrite} />
    </div>
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
      {writing ? "Saving..." : "Save Entry"} <kbd>⌃Enter</kbd>
    </button>
  </div>

  {#if cowrite.isActive}
    <CowritePanel {cowrite} />
  {/if}
</form>

<svelte:window onkeydown={handleFormKeydown} />

<style>
  .journal-write-form { padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; position: relative; }
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label { font-size: 0.8rem; color: #7c7c9a; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .field input, .field textarea {
    background: #16213e; border: 1px solid #333; color: #e0e0e0;
    padding: 0.5rem; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
  }
  .field textarea { resize: vertical; min-height: 200px; font-family: inherit; line-height: 1.5; }
  .textarea-actions { display: flex; flex-direction: column; gap: 0.3rem; }
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
