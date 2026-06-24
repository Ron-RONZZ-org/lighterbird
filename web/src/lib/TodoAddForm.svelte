<script>
  /** Todo creation form — used when !todo add is typed interactively. */

  let { initialData = {}, onsubmit } = $props();

  let title = $state(initialData.title || "");
  let description = $state(initialData.description || "");
  let priority = $state(initialData.priority || "5");
  let due = $state(initialData.due || "");
  let adding = $state(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!title) return;
    adding = true;
    try {
      const flags = { priority };
      if (due) flags.due = due;
      if (description) flags.description = description;
      await onsubmit({
        tokens: ["todo", "add"],
        flags,
        remaining: [title],
      });
    } finally {
      adding = false;
    }
  }
</script>

<form onsubmit={handleSubmit} class="todo-add-form">
  <div class="field">
    <label for="title">Title</label>
    <input id="title" type="text" bind:value={title} required placeholder="What needs to be done?" />
  </div>
  <div class="field">
    <label for="description">Description</label>
    <textarea id="description" bind:value={description} rows="4" placeholder="Optional details..."></textarea>
  </div>
  <div class="row-fields">
    <div class="field">
      <label for="priority">Priority (1-10)</label>
      <input id="priority" type="number" bind:value={priority} min="1" max="10" />
    </div>
    <div class="field">
      <label for="due">Due Date</label>
      <input id="due" type="date" bind:value={due} />
    </div>
  </div>
  <div class="actions">
    <button type="submit" disabled={adding || !title}>
      {adding ? "Adding..." : "Add Todo"}
    </button>
  </div>
</form>

<style>
  .todo-add-form { padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
  .row-fields { display: flex; gap: 0.75rem; }
  .row-fields .field { flex: 1; }
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label { font-size: 0.8rem; color: #7c7c9a; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .field input, .field textarea {
    background: #16213e; border: 1px solid #333; color: #e0e0e0;
    padding: 0.5rem; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
  }
  .field textarea { resize: vertical; min-height: 80px; font-family: inherit; line-height: 1.5; }
  .actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
  .actions button {
    background: #0f3460; color: #e0e0e0; border: none; padding: 0.5rem 1.5rem;
    border-radius: 4px; cursor: pointer; font-size: 0.9rem;
  }
  .actions button:disabled { opacity: 0.5; cursor: not-allowed; }
  .actions button:hover:not(:disabled) { background: #1a4a7a; }
</style>
