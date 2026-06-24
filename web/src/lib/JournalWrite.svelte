<script>
  /** Journal entry write form — used when !journal write is typed interactively. */

  let { initialData = {}, onsubmit } = $props();
  // svelte-ignore state_referenced_locally
  const _initial = initialData;

  let title = $state(_initial.title || "");
  let text = $state(_initial.text || "");
  let date = $state(_initial.date || new Date().toISOString().slice(0, 10));
  let writing = $state(false);

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
    <textarea id="text" bind:value={text} rows="12" placeholder="Write your journal entry here..."></textarea>
  </div>
  <div class="actions">
    <button type="submit" disabled={writing || !title}>
      {writing ? "Saving..." : "Save Entry"}
    </button>
  </div>
</form>

<style>
  .journal-write-form { padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label { font-size: 0.8rem; color: #7c7c9a; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
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
</style>
