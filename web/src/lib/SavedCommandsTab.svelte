<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { execute } from "./commandExecutor.js";

  let { data = {} } = $props();
  let commands = $derived(data?.commands || []);
  let total = $derived(data?.total || 0);

  // Inline add/edit form state
  let showForm = $state(false);
  let editingAlias = $state("");
  let formAlias = $state("");
  let formCommand = $state("");
  let formHint = $state("");

  function openAddForm() {
    editingAlias = "";
    formAlias = "";
    formCommand = "";
    formHint = "";
    showForm = true;
  }

  function openEditForm(cmd) {
    editingAlias = cmd.alias;
    formAlias = cmd.alias;
    formCommand = cmd.command_template;
    formHint = cmd.hint || "";
    showForm = true;
  }

  function closeForm() {
    showForm = false;
    editingAlias = "";
    formAlias = "";
    formCommand = "";
    formHint = "";
  }

  async function handleSave() {
    const alias = formAlias.trim();
    const cmdTemplate = formCommand.trim();
    const hint = formHint.trim();
    if (!alias || !cmdTemplate) return;

    let input;
    if (editingAlias) {
      // Modify existing
      input = `!user saved-commands modify ${editingAlias}` +
        ` --alias ${alias}` +
        ` --command "${cmdTemplate}"` +
        (hint ? ` --hint "${hint}"` : "");
    } else {
      // New
      input = `!user saved-commands add --alias ${alias} --command "${cmdTemplate}"` +
        (hint ? ` --hint "${hint}"` : "");
    }

    try {
      const result = await execute(input);
      if (result.type === "status") {
        // Refresh the list
        const refreshed = await execute("!user saved-commands list");
        if (refreshed.type === "saved-commands") {
          tabStore.update(tabStore.active.id, refreshed);
        }
        closeForm();
      } else {
        tabStore.open("error", "Error", {
          message: result.data?.message || "Failed to save command",
        });
      }
    } catch (err) {
      tabStore.open("error", "Error", {
        message: err.message || "Failed to save command",
      });
    }
  }

  async function handleDelete(cmdAlias) {
    if (!confirm(`Delete saved command "${cmdAlias}"?`)) return;
    try {
      const result = await execute(`!user saved-commands remove ${cmdAlias}`);
      if (result.type === "status") {
        const refreshed = await execute("!user saved-commands list");
        if (refreshed.type === "saved-commands") {
          tabStore.update(tabStore.active.id, refreshed);
        }
      }
    } catch (err) {
      tabStore.open("error", "Error", {
        message: err.message || "Failed to delete command",
      });
    }
  }

  async function handleUse(cmdAlias, cmdTemplate) {
    // Copy the template to the command bar (the user can then add $1 etc.)
    // We signal via a custom event that the parent can pick up
    const event = new CustomEvent("fill-command", {
      detail: { template: cmdTemplate, alias: cmdAlias },
    });
    window.dispatchEvent(event);
  }

  function truncate(s, max) {
    if (!s) return "";
    return s.length > max ? s.slice(0, max - 1) + "…" : s;
  }
</script>

<div class="saved-commands-tab">
  <!-- Toolbar -->
  <div class="toolbar">
    <span class="title">Saved Commands ({total})</span>
    <button class="btn-add" onclick={openAddForm}>+ New Saved Command</button>
  </div>

  <!-- Inline Add/Edit Form -->
  {#if showForm}
    <div class="form-card">
      <h3>{editingAlias ? `Edit: ${editingAlias}` : "New Saved Command"}</h3>
      <div class="form-row">
        <label>
          <span class="label-text">Alias</span>
          <input type="text" bind:value={formAlias} placeholder="e.g. ronzz" />
        </label>
      </div>
      <div class="form-row">
        <label>
          <span class="label-text">Command <em>(without !, use $1 $2 … for args)</em></span>
          <input type="text" bind:value={formCommand} placeholder="e.g. email list --folder ron@ronzz.org/$1" />
        </label>
      </div>
      <div class="form-row">
        <label>
          <span class="label-text">Hint</span>
          <input type="text" bind:value={formHint} placeholder="Short description" />
        </label>
      </div>
      <div class="form-actions">
        <button class="btn-primary" onclick={handleSave}>Save</button>
        <button class="btn-cancel" onclick={closeForm}>Cancel</button>
      </div>
    </div>
  {/if}

  <!-- List -->
  <div class="list">
    {#each commands as cmd (cmd.uuid)}
      <div class="row">
        <span class="cell alias-cell">
          <code class="alias">!{cmd.alias}</code>
        </span>
        <span class="cell template-cell">{truncate(cmd.command_template, 50)}</span>
        <span class="cell hint-cell">{cmd.hint || ""}</span>
        <span class="cell actions-cell">
          <button class="btn-use" onclick={() => handleUse(cmd.alias, cmd.command_template)} title="Use in command bar">Use</button>
          <button class="btn-edit" onclick={() => openEditForm(cmd)} title="Edit">Edit</button>
          <button class="btn-delete" onclick={() => handleDelete(cmd.alias)} title="Delete">×</button>
        </span>
      </div>
    {:else}
      <p class="empty">No saved commands yet. Click "+ New Saved Command" to add one.</p>
    {/each}
  </div>
</div>

<style>
  .saved-commands-tab {
    display: flex;
    flex-direction: column;
    height: 100%;
    font-family: monospace;
    font-size: 0.85rem;
  }
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 0.75rem;
    border-bottom: 1px solid #333;
  }
  .title {
    color: #e0e0e0;
    font-weight: 600;
  }
  .btn-add {
    background: #2a4a2a;
    color: #6aaa6a;
    border: 1px solid #3a6a3a;
    border-radius: 6px;
    padding: 0.3rem 0.8rem;
    font-family: monospace;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .btn-add:hover { background: #3a5a3a; }

  .form-card {
    margin: 0.5rem 0.75rem;
    padding: 0.75rem;
    background: #1e1e32;
    border: 1px solid #4a4a6a;
    border-radius: 8px;
  }
  .form-card h3 {
    margin: 0 0 0.5rem;
    font-size: 0.9rem;
    color: #e0e0e0;
  }
  .form-row { margin-bottom: 0.4rem; }
  .form-row label {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  .label-text {
    font-size: 0.78rem;
    color: #7c7c9a;
  }
  .label-text em {
    color: #5a5a7a;
    font-style: normal;
  }
  .form-row input {
    background: #16162a;
    border: 1px solid #333;
    border-radius: 4px;
    padding: 0.35rem 0.5rem;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
    outline: none;
  }
  .form-row input:focus { border-color: #5a5a8a; }
  .form-actions {
    display: flex;
    gap: 0.4rem;
    margin-top: 0.5rem;
  }
  .btn-primary {
    background: #2a4a2a;
    color: #6aaa6a;
    border: 1px solid #3a6a3a;
    border-radius: 6px;
    padding: 0.3rem 0.8rem;
    font-family: monospace;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .btn-primary:hover { background: #3a5a3a; }
  .btn-cancel {
    background: transparent;
    color: #7c7c9a;
    border: 1px solid #444;
    border-radius: 6px;
    padding: 0.3rem 0.8rem;
    font-family: monospace;
    font-size: 0.8rem;
    cursor: pointer;
  }
  .btn-cancel:hover { background: #2a2a3e; }

  .list {
    flex: 1;
    overflow-y: auto;
  }
  .row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.4rem 0.75rem;
    border-bottom: 1px solid #2a2a3e;
    transition: background 0.08s;
  }
  .row:hover { background: #2a2a44; }
  .cell { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .alias-cell { min-width: 8rem; flex-shrink: 0; }
  .alias {
    background: #1a1a30;
    padding: 0.1rem 0.4rem;
    border-radius: 4px;
    color: #8a8acc;
    font-size: 0.82rem;
  }
  .template-cell { flex: 1; color: #ccc; min-width: 0; }
  .hint-cell {
    min-width: 8rem;
    color: #7c7c9a;
    font-size: 0.78rem;
    flex-shrink: 0;
  }
  .actions-cell {
    display: flex;
    gap: 0.25rem;
    flex-shrink: 0;
  }
  .btn-use, .btn-edit {
    background: transparent;
    color: #7c7c9a;
    border: 1px solid #444;
    border-radius: 4px;
    padding: 0.15rem 0.5rem;
    font-family: monospace;
    font-size: 0.75rem;
    cursor: pointer;
  }
  .btn-use:hover { background: #2a4a2a; color: #6aaa6a; border-color: #3a6a3a; }
  .btn-edit:hover { background: #3a3a5a; color: #c0c0e0; }
  .btn-delete {
    background: transparent;
    color: #8a4a4a;
    border: 1px solid #5a3a3a;
    border-radius: 4px;
    padding: 0.15rem 0.4rem;
    font-family: monospace;
    font-size: 0.8rem;
    cursor: pointer;
    line-height: 1;
  }
  .btn-delete:hover { background: #4a2a2a; color: #cc6a6a; }
  .empty {
    color: #7c7c9a;
    text-align: center;
    padding: 2rem;
  }
</style>
