<script>
  /**
   * Blocking popup form for creating/editing a calendar account.
   *
   * Props:
   *   calendar  — null for new, or calendar object for edit
   *   onSaved  — called after successful save
   *   onDismiss — called when user closes the dialog
   */

  import { calendar as calendarApi } from "./api.js";

  let { calendar = null, initialData = null, onSaved = () => {}, onDismiss = () => {} } = $props();

  let isEdit = $derived(calendar !== null);

  // svelte-ignore state_referenced_locally
  const _init = calendar || initialData || {};
  let url = $state(_init.url || "");
  let username = $state(_init.username || "");
  let password = $state("");
  let saving = $state(false);
  let error = $state("");

  async function handleSave() {
    if (!url.trim()) {
      error = "Calendar URL is required.";
      return;
    }
    saving = true;
    error = "";
    try {
      if (isEdit) {
        const updates = {};
        if (url.trim()) updates.url = url.trim();
        if (username) updates.username = username;
        if (password) updates.password = password;
        await calendarApi.updateCalendar(calendar.uuid, updates);
      } else {
        await calendarApi.createCalendar({
          url: url.trim(),
          username: username,
          password: password,
          remote: 1,
        });
      }
      onSaved();
    } catch (err) {
      error = err.message || "Failed to save calendar.";
    } finally {
      saving = false;
    }
  }
</script>

<div class="modal-overlay" onclick={onDismiss} onkeydown={(e) => e.key === "Escape" && onDismiss()} role="button" tabindex="-1" aria-label="Dismiss">
  <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" tabindex="0" onkeydown={() => {}}>
    <div class="modal-header">
      <h2>{isEdit ? "Edit Calendar" : "Add Calendar"}</h2>
      <p class="subtitle">{isEdit ? `Editing "${calendar.url}"` : "Configure a new calendar"}</p>
    </div>
    <div class="form">
      <label class="field">
        <span class="field-label">CalDAV URL</span>
        <input type="url" class="text-input" bind:value={url} placeholder="https://your-caldav-server.com" autofocus />
      </label>
      <label class="field">
        <span class="field-label">Username</span>
        <input type="text" class="text-input" bind:value={username} placeholder="username" />
      </label>
      <label class="field">
        <span class="field-label">Password</span>
        <input type="password" class="text-input" bind:value={password} placeholder={isEdit ? "Leave blank to keep current" : "Required"} />
      </label>
      {#if error}
        <p class="error">{error}</p>
      {/if}
      <div class="form-actions">
        <button class="btn-primary" onclick={handleSave} disabled={saving || !url.trim() || (!isEdit && !password)}>
          {saving ? "Saving…" : isEdit ? "Update" : "Add Calendar"}
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
    width: 420px;
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
  .field-label { font-size: 0.78rem; color: #7c7c9a; font-family: monospace; }
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
