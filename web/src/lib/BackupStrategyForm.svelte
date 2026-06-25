<script>
  /**
   * Modal popup form for adding/editing a backup strategy.
   *
   * Props:
   *   strategy  — null for new, or strategy object for edit
   *   onSaved   — called after successful save
   *   onDismiss — called when user closes the form
   */

  let { strategy = null, onSaved = () => {}, onDismiss = () => {} } = $props();

  let isEdit = $derived(strategy !== null);
  const _init = strategy || {};

  let id = $state(_init.id || "");
  let label = $state(_init.label || _init.id || "");
  let schedule = $state(_init.schedule || "manual");
  let maxCopies = $state(_init.max_copies || 10);
  let target = $state(_init.target || "local");
  let enabled = $state(_init.enabled !== undefined ? _init.enabled : true);
  let saving = $state(false);
  let error = $state("");

  let validationError = $derived.by(() => {
    if (!id.trim() && !isEdit) return "Strategy ID is required.";
    if (!isEdit && !/^[a-z][a-z0-9-]*$/.test(id.trim())) return "ID must start with a letter and contain only lowercase letters, digits, and hyphens.";
    if (maxCopies < 1) return "Max copies must be >= 1.";
    return "";
  });

  async function handleSave() {
    if (validationError) {
      error = validationError;
      return;
    }
    saving = true;
    error = "";

    try {
      const flags = {};
      if (!isEdit) {
        flags.id = id.trim();
      }
      flags.label = label.trim() || id.trim();
      flags.schedule = schedule;
      flags.max_copies = String(maxCopies);
      flags.target = target.trim() || "local";
      flags.enabled = enabled ? "true" : "false";

      const tokens = isEdit
        ? ["backup", "config", "modify", strategy.id]
        : ["backup", "config", "add"];

      const resp = await fetch("/api/v1/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tokens, flags, raw_input: "!" + tokens.join(" ") }),
      });
      const result = await resp.json();
      if (!resp.ok) {
        const detail = result.detail || {};
        const msg = typeof detail === "string" ? detail : detail.error || `HTTP ${resp.status}`;
        throw new Error(msg);
      }
      onSaved();
    } catch (err) {
      error = err.message || "Failed to save strategy.";
    } finally {
      saving = false;
    }
  }
</script>

<div class="modal-overlay" onclick={onDismiss} onkeydown={(e) => e.key === "Escape" && onDismiss()} role="button" tabindex="-1" aria-label="Dismiss">
  <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" tabindex="0">
    <div class="modal-header">
      <h2>{isEdit ? "Edit Backup Strategy" : "Add Backup Strategy"}</h2>
      <p class="subtitle">{isEdit ? `Editing "${strategy.label || strategy.id}"` : "Configure a new backup strategy"}</p>
    </div>
    <div class="form">
      {#if !isEdit}
        <label class="field">
          <span class="field-label">Strategy ID</span>
          <input type="text" class="text-input" bind:value={id} placeholder="daily" autofocus disabled={isEdit} />
          <span class="field-hint">Lowercase letters, digits, hyphens. Must start with a letter.</span>
        </label>
      {/if}
      <label class="field">
        <span class="field-label">Label</span>
        <input type="text" class="text-input" bind:value={label} placeholder="Daily backups" />
      </label>
      <label class="field">
        <span class="field-label">Schedule</span>
        <select class="text-input" bind:value={schedule}>
          <option value="manual">Manual (only via !backup now)</option>
          <option value="hourly">Hourly</option>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly</option>
        </select>
      </label>
      <label class="field">
        <span class="field-label">Max Copies</span>
        <input type="number" class="text-input" bind:value={maxCopies} min="1" />
      </label>
      <label class="field">
        <span class="field-label">Target</span>
        <input type="text" class="text-input" bind:value={target} placeholder="local" />
        <span class="field-hint">"local" for default backups directory, or an absolute path.</span>
      </label>
      <label class="field field-row">
        <input type="checkbox" bind:checked={enabled} />
        <span class="field-label">Enabled</span>
      </label>
      {#if error}
        <p class="error">{error}</p>
      {/if}
      <div class="form-actions">
        <button class="btn-primary" onclick={handleSave} disabled={saving || (!isEdit && !id.trim()) || maxCopies < 1}>
          {saving ? "Saving…" : isEdit ? "Update" : "Add Strategy"}
        </button>
        <button class="btn-secondary" onclick={onDismiss}>Cancel</button>
      </div>
    </div>
  </div>
</div>

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 500;
    display: flex;
    align-items: center;
    justify-content: center;
    animation: fadeIn 0.15s ease;
  }
  @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
  .modal {
    background: #1e1e32;
    border: 1px solid #444;
    border-radius: 16px;
    padding: 1.5rem;
    width: 460px;
    max-width: 90vw;
    max-height: 80vh;
    overflow-y: auto;
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
  }
  .modal-header { margin-bottom: 1rem; }
  .modal-header h2 { font-size: 1.1rem; color: #e0e0e0; font-weight: 600; }
  .subtitle { font-size: 0.8rem; color: #7c7c9a; margin-top: 0.25rem; }
  .form { display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.3rem; }
  .field-row { flex-direction: row; align-items: center; gap: 0.5rem; }
  .field-label { font-size: 0.78rem; color: #7c7c9a; font-family: monospace; }
  .field-hint { font-size: 0.7rem; color: #5a5a7a; font-style: italic; }
  .text-input {
    background: #2a2a3e;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 0.5rem 0.7rem;
    color: #e0e0e0;
    font-size: 0.85rem;
    outline: none;
    font-family: monospace;
  }
  .text-input:focus { border-color: #7c7c9a; }
  select.text-input { cursor: pointer; }
  .error { color: #aa6a6a; font-size: 0.8rem; }
  .form-actions { display: flex; gap: 0.5rem; margin-top: 0.25rem; }
  .btn-primary, .btn-secondary {
    padding: 0.45rem 1rem;
    border-radius: 8px;
    border: 1px solid #444;
    font-family: monospace;
    font-size: 0.85rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-primary {
    background: #3a6a3a;
    color: #e0e0e0;
    border-color: #4a8a4a;
    flex: 1;
  }
  .btn-primary:hover { background: #4a8a4a; }
  .btn-primary:disabled { opacity: 0.4; cursor: default; }
  .btn-secondary { background: #2a2a3e; color: #b0b0c0; }
  .btn-secondary:hover { background: #3a3a5a; }
</style>
