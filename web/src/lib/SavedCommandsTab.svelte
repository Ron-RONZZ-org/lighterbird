<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { execute } from "./commandExecutor.js";

  let { data = {} } = $props();
  let commands = $derived(data?.commands || []);
  let total = $derived(data?.total || 0);

  function openAddForm() {
    tabStore.open("form", "New Saved Command", {
      form: "user-saved-commands-add",
      initialData: {},
    }, { idKey: "user-saved-commands-add" });
  }

  function openEditForm(cmd) {
    tabStore.open("form", `Edit: ${cmd.alias}`, {
      form: "user-saved-commands-modify",
      initialData: {
        alias: cmd.alias,
        command: cmd.command_template,
        hint: cmd.hint || "",
      },
    }, { idKey: "user-saved-commands-edit" });
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
