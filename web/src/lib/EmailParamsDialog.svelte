<script>
  let {
    config,
    onSave = () => {},
    onActivate = () => {},
    onDelete = () => {},
    onClose = () => {},
  } = $props();

  let configDialogName = $state("");
  let userConfigs = $state({});

  $effect(() => {
    userConfigs = config.getUserConfigs();
  });

  function handleSaveConfig() {
    const name = configDialogName.trim();
    if (!name) return;
    onSave(name);
    configDialogName = "";
  }
</script>

<div class="params-panel">
  <div class="params-header">
    <h4>Parameters</h4>
    <button class="close-btn" onclick={onClose} aria-label="Close">✕</button>
  </div>

  <!-- Save / Load section -->
  <div class="params-section">
    <h5>Save Current View</h5>
    <div class="save-row">
      <input type="text" class="params-input" bind:value={configDialogName}
        placeholder="Config name..." onkeydown={(e) => { if (e.key === "Enter") handleSaveConfig(); }} />
      <button class="btn-sm" onclick={handleSaveConfig} disabled={!configDialogName.trim()}>Save</button>
    </div>
  </div>

  <!-- Manage configs -->
  <div class="params-section">
    <h5>Saved Configs</h5>
    {#if Object.keys(userConfigs).length === 0}
      <p class="empty-msg">No saved configs yet.</p>
    {:else}
      <div class="config-list">
        {#each Object.entries(userConfigs) as [name, cfg]}
          <div class="config-item" class:active={config.getActiveConfigName() === name}>
            <label class="config-check">
              <input type="checkbox" />
              <span class="config-name">{name}</span>
            </label>
            <div class="config-actions">
              <button class="btn-tiny" onclick={() => onActivate(name)}
                disabled={config.getActiveConfigName() === name}
                title="Activate">Activate</button>
              <button class="btn-tiny danger" onclick={() => onDelete(name)} title="Delete">✕</button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</div>

<style>
  .params-panel {
    width: 360px;
    padding: 0;
  }
  .params-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid #333;
  }
  .params-header h4 {
    margin: 0;
    font-size: 0.85rem;
    color: #e0e0e0;
  }
  .close-btn {
    background: none; border: none; color: #7c7c9a; cursor: pointer;
    font-size: 0.9rem; padding: 0.1rem 0.3rem;
  }
  .close-btn:hover { color: #e0e0e0; }
  .params-section {
    padding: 0.6rem 0.75rem;
    border-bottom: 1px solid #2a2a3e;
  }
  .params-section:last-child { border-bottom: none; }
  .params-section h5 {
    margin: 0 0 0.4rem;
    font-size: 0.72rem;
    color: var(--clr-muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .save-row {
    display: flex;
    gap: 0.4rem;
  }
  .params-input {
    flex: 1;
    padding: 0.3rem 0.5rem;
    background: #16213e; border: 1px solid #333; color: #e0e0e0;
    border-radius: 4px; font-family: monospace; font-size: 0.82rem; outline: none;
  }
  .params-input:focus { border-color: #5a5a8a; }
  .btn-sm {
    padding: 0.3rem 0.6rem; border: 1px solid #444; border-radius: 4px;
    background: #2a2a3e; color: #e0e0e0; cursor: pointer;
    font-family: monospace; font-size: 0.78rem;
  }
  .btn-sm:hover { background: #3a3a5a; }
  .btn-sm:disabled { opacity: 0.4; cursor: default; }
  .empty-msg {
    color: var(--clr-muted); font-size: 0.78rem; text-align: center; padding: 0.5rem;
  }
  .config-list {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    max-height: 200px;
    overflow-y: auto;
  }
  .config-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.3rem 0.4rem;
    border-radius: 4px;
    font-size: 0.8rem;
  }
  .config-item:hover { background: #2a2a44; }
  .config-item.active { background: #2a2a50; border: 1px solid #4a4a6a; }
  .config-check {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    cursor: pointer;
    flex: 1;
  }
  .config-check input { width: 0.85rem; height: 0.85rem; accent-color: #4a6fa5; }
  .config-name { color: #e0e0e0; }
  .config-actions { display: flex; gap: 0.25rem; }
  .btn-tiny {
    padding: 0.15rem 0.4rem; border: 1px solid #444; border-radius: 3px;
    background: #2a2a3e; color: #b0b0c0; cursor: pointer;
    font-family: monospace; font-size: 0.7rem;
  }
  .btn-tiny:hover { background: #3a3a5a; }
  .btn-tiny.danger { border-color: #5a3a3a; color: #8a4a4a; }
  .btn-tiny.danger:hover { background: #4a2a2a; color: #cc6a6a; }
  .btn-tiny:disabled { opacity: 0.4; cursor: default; }
</style>
