<script>
  /** Rendered todo detail view — markdown description, template fields, modify support. */

  import { renderMarkdown } from "./markdown.js";
  import { todo as todoApi } from "./api.js";
  import { tabStore } from "./tabStore.svelte.js";
  import { formatListItemDate } from "./listTabShared.svelte.js";

  let { data: _data = {} } = $props();

  let todo = $state({});
  let editing = $state(false);
  let editTitle = $state("");
  let editDescription = $state("");
  let editPriority = $state("5");
  let editDue = $state("");
  let editStatus = $state("pending");
  let editParentUuid = $state("");
  let saving = $state(false);

  // Sync from props when data changes
  $effect(() => {
    const d = _data;
    if (d && d.uuid) {
      todo = d;
      if (!editing) {
        editTitle = d.title || "";
        editDescription = d.description || "";
        editPriority = String(d.priority || "5");
        editDue = d.due || "";
        editStatus = d.status || "pending";
        editParentUuid = d.parent_uuid || "";
      }
    }
  });

  // Template fields from priskribo JSON
  let tplFields = $derived.by(() => {
    try {
      const parsed = JSON.parse(todo.description || "{}");
      if (typeof parsed === "object" && !Array.isArray(parsed)) {
        return Object.entries(parsed).filter(([k]) => !k.startsWith("_"));
      }
    } catch {}
    return [];
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
  }

  function startEdit() {
    editing = true;
    editTitle = todo.title || "";
    editDescription = todo.description || "";
    editPriority = String(todo.priority || "5");
    editDue = todo.due || "";
    editStatus = todo.status || "pending";
    editParentUuid = todo.parent_uuid || "";
  }

  function cancelEdit() {
    editing = false;
  }

  async function saveEdit() {
    saving = true;
    try {
      const updates = {
        title: editTitle,
        description: editDescription,
        priority: parseInt(editPriority, 10) || 5,
        status: editStatus,
      };
      if (editDue) updates.due = editDue;
      if (editParentUuid) updates.parent_uuid = editParentUuid;
      else updates.parent_uuid = null;

      await todoApi.update(todo.uuid, updates);
      // Refresh
      const refreshed = await todoApi.get(todo.uuid);
      todo = refreshed;
      editing = false;
    } catch (err) {
      // Error handled by caller
    } finally {
      saving = false;
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="todo-view">
  <!-- Toolbar -->
  <div class="toolbar">
    <div class="left">
      {#if editing}
        <button class="tool-btn" onclick={cancelEdit}>Cancel</button>
      {:else}
        <button class="tool-btn" onclick={startEdit} title="Edit (i)">✎ Edit <kbd>i</kbd></button>
      {/if}
    </div>
    <div class="center">
      <span class="hint">{editing ? "Editing…" : `${todo.status === "done" ? "✓ done" : "○ pending"}`}</span>
    </div>
    <div class="right">
      {#if editing}
        <button class="tool-btn primary" onclick={saveEdit} disabled={saving || !editTitle}>
          {saving ? "Saving…" : "Save"}
        </button>
      {/if}
    </div>
  </div>

  <!-- Content -->
  <div class="content">
    {#if editing}
      <!-- Edit mode -->
      <div class="edit-form">
        <div class="field">
          <label for="ev-title">Title</label>
          <input id="ev-title" type="text" bind:value={editTitle} required />
        </div>
        <div class="field">
          <label for="ev-desc">Description <span class="field-hint">(markdown)</span></label>
          <textarea id="ev-desc" bind:value={editDescription} rows="6"></textarea>
        </div>
        <div class="row-fields">
          <div class="field">
            <label for="ev-priority">Priority</label>
            <input id="ev-priority" type="number" bind:value={editPriority} min="1" max="10" />
          </div>
          <div class="field">
            <label for="ev-due">Due</label>
            <input id="ev-due" type="date" bind:value={editDue} />
          </div>
          <div class="field">
            <label for="ev-status">Status</label>
            <select id="ev-status" bind:value={editStatus}>
              <option value="pending">pending</option>
              <option value="done">done</option>
            </select>
          </div>
        </div>
        <div class="field">
          <label for="ev-parent">Parent UUID</label>
          <input id="ev-parent" type="text" bind:value={editParentUuid} placeholder="(empty for root)" />
        </div>
      </div>
    {:else}
      <!-- View mode -->
      <h1 class="title">{todo.title || "(untitled)"}</h1>

      <div class="meta-row">
        <span class="meta-badge priority-{priorityClass(todo.priority)}">Prio {todo.priority}</span>
        <span class="meta-badge status-{todo.status}">{todo.status}</span>
        {#if todo.due}
          <span class="meta-badge due">Due {todo.due}</span>
        {/if}
        <span class="meta-date">Created {formatListItemDate(todo.created_at)}</span>
      </div>

      <!-- Description rendered as markdown -->
      {#if todo.description}
        <div class="description">
          {@html renderMarkdown(todo.description)}
        </div>
      {:else if tplFields.length > 0}
        <!-- No separate description — template values stored in description JSON -->
      {:else}
        <p class="empty-desc">No description.</p>
      {/if}

      <!-- Template fields rendered -->
      {#if tplFields.length > 0}
        <div class="tpl-section">
          <h3>Template Fields</h3>
          {#each tplFields as [name, value]}
            <div class="tpl-field">
              <span class="tpl-label">{name}</span>
              <div class="tpl-value">
                {#if name === "agenda" || value.length > 100 || value.includes("\n")}
                  {@html renderMarkdown(value)}
                {:else}
                  {value}
                {/if}
              </div>
            </div>
          {/each}
        </div>
      {/if}

      <!-- Children (subtasks) -->
      {#if todo.children && todo.children.length > 0}
        <div class="section">
          <h3>Subtasks ({todo.children.length})</h3>
          <div class="child-list">
            {#each todo.children as child}
              <div class="child-row">
                <span class="child-status">{child.stato === "done" ? "✓" : "○"}</span>
                <span class="child-title">{child.titolo}</span>
              </div>
            {/each}
          </div>
        </div>
      {/if}

      <!-- Dependencies -->
      {#if todo.dependencies && todo.dependencies.length > 0}
        <div class="section">
          <h3>Depends On</h3>
          <div class="child-list">
            {#each todo.dependencies as dep}
              <div class="child-row">
                <span class="child-status">{dep.status === "done" ? "✓" : "○"}</span>
                <span class="child-title">{dep.title}</span>
              </div>
            {/each}
          </div>
        </div>
      {/if}

      <!-- Blocked tasks -->
      {#if todo.blocked_tasks && todo.blocked_tasks.length > 0}
        <div class="section">
          <h3>Blocks</h3>
          <div class="child-list">
            {#each todo.blocked_tasks as bt}
              <div class="child-row">
                <span class="child-status">{bt.status === "done" ? "✓" : "○"}</span>
                <span class="child-title">{bt.title}</span>
              </div>
            {/each}
          </div>
        </div>
      {/if}

      <!-- Attachments -->
      {#if todo.attachments && todo.attachments.length > 0}
        <div class="section">
          <h3>Attachments</h3>
          <div class="attach-list">
            {#each todo.attachments as att}
              <div class="attach-row">
                <span class="attach-name">{att.origina_nomo}</span>
                {#if att.origina_vojo}
                  <a class="attach-link" href={att.origina_vojo} target="_blank" rel="noopener">↗</a>
                {/if}
                <span class="attach-size">{att.grandeco > 0 ? `${(att.grandeco / 1024).toFixed(0)} KB` : ""}</span>
                <span class="attach-sync sync-{att.sync_stato}">{att.sync_stato}</span>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    {/if}
  </div>
</div>

<script context="module">
  function priorityClass(p) {
    const n = typeof p === "string" ? parseInt(p, 10) : p;
    if (!n) return "low";
    if (n >= 8) return "high";
    if (n >= 4) return "mid";
    return "low";
  }
</script>

<style>
  .todo-view {
    display: flex; flex-direction: column; height: 100%;
    font-size: 0.9rem; position: relative;
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
    flex: 1; overflow-y: auto; padding: 1rem 1.2rem;
  }
  .title {
    font-size: 1.3rem; font-weight: 700; color: #e0e0e0;
    margin: 0 0 0.5rem; line-height: 1.3;
  }
  .meta-row {
    display: flex; align-items: center; gap: 0.5rem;
    margin-bottom: 1rem; flex-wrap: wrap;
  }
  .meta-badge {
    font-size: 0.7rem; padding: 0.15rem 0.45rem; border-radius: 3px;
    font-family: monospace; text-transform: uppercase;
  }
  .priority-high { background: #4b2020; color: #e07070; }
  .priority-mid { background: #4a3a20; color: #d0b060; }
  .priority-low { background: #2a2a3e; color: var(--clr-muted); }
  .status-pending { background: #1e2a3e; color: #7ca8d0; }
  .status-done { background: #1e3a2e; color: #7fd0a0; }
  .due { background: #2a2a3e; color: var(--clr-muted); }
  .meta-date { color: var(--clr-muted); font-size: 0.75rem; }
  .description {
    background: #16162a; border: 1px solid #2a2a3e; border-radius: 4px;
    padding: 0.75rem 1rem; line-height: 1.6; margin-bottom: 1rem;
  }
  .description :global(p) { margin: 0 0 0.5rem; }
  .description :global(p:last-child) { margin-bottom: 0; }
  .description :global(code) {
    background: #1a1a2e; padding: 0.1rem 0.3rem; border-radius: 3px;
    font-size: 0.82rem;
  }
  .description :global(pre) {
    background: #1a1a2e; padding: 0.6rem; border-radius: 4px;
    overflow-x: auto; font-size: 0.82rem; margin: 0.5rem 0;
  }
  .empty-desc { color: var(--clr-muted); font-style: italic; padding: 0.5rem 0; }
  .tpl-section {
    border: 1px solid #2a2a3e; border-radius: 4px; padding: 0.75rem;
    background: #14142a; margin-bottom: 1rem;
  }
  .tpl-section h3 {
    margin: 0 0 0.6rem; font-size: 0.75rem; color: var(--clr-muted);
    text-transform: uppercase; letter-spacing: 0.08em;
  }
  .tpl-field {
    margin-bottom: 0.6rem; padding-bottom: 0.6rem;
    border-bottom: 1px solid #2a2a3e;
  }
  .tpl-field:last-child { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }
  .tpl-label {
    display: block; font-size: 0.72rem; color: var(--clr-sub);
    text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.2rem;
  }
  .tpl-value { color: #e0e0e0; font-size: 0.88rem; line-height: 1.5; }
  .tpl-value :global(p) { margin: 0 0 0.3rem; }
  .tpl-value :global(code) {
    background: #1a1a2e; padding: 0.1rem 0.3rem; border-radius: 3px;
    font-size: 0.8rem;
  }
  .section { margin-bottom: 1rem; }
  .section h3 {
    font-size: 0.75rem; color: var(--clr-muted);
    text-transform: uppercase; letter-spacing: 0.08em; margin: 0 0 0.4rem;
  }
  .child-list, .attach-list {
    border: 1px solid #2a2a3e; border-radius: 4px; overflow: hidden;
  }
  .child-row, .attach-row {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.35rem 0.6rem; border-bottom: 1px solid #2a2a3e;
    font-size: 0.85rem;
  }
  .child-row:last-child, .attach-row:last-child { border-bottom: none; }
  .child-status { color: var(--clr-muted); width: 1.2rem; text-align: center; }
  .child-title { color: #e0e0e0; flex: 1; }
  .attach-name { color: #e0e0e0; flex: 1; }
  .attach-link { color: #6a8aaa; text-decoration: none; font-size: 0.85rem; }
  .attach-link:hover { color: #8ab0d0; }
  .attach-size { color: var(--clr-muted); font-size: 0.75rem; font-family: monospace; }
  .attach-sync { font-size: 0.68rem; font-family: monospace; text-transform: uppercase; }
  .sync-synced { color: #6aaa6a; }
  .sync-pending { color: #a0a060; }
  .sync-error { color: #d07070; }
  /* Edit mode */
  .edit-form { display: flex; flex-direction: column; gap: 0.75rem; }
  .row-fields { display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .row-fields .field { flex: 1; min-width: 120px; }
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label {
    font-size: 0.78rem; color: var(--clr-sub); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em;
  }
  .field-hint {
    font-weight: 400; text-transform: none; letter-spacing: 0;
    color: var(--clr-dim); font-size: 0.7rem;
  }
  .field input, .field textarea, .field select {
    background: #16213e; border: 1px solid #333; color: #e0e0e0;
    padding: 0.5rem 0.6rem; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
    outline: none; transition: border-color 0.15s;
  }
  .field input:focus, .field textarea:focus, .field select:focus {
    border-color: #5a5a8a;
  }
  .field textarea { resize: vertical; min-height: 80px; font-family: inherit; line-height: 1.5; }
</style>
