<script>
  /**
   * Blocking popup form for creating/editing an email account.
   *
   * Props:
   *   account  — null for new, or account object for edit
   *   onSaved  — called after successful save
   *   onDismiss — called when user closes the dialog
   */

  import { email as emailApi } from "./api.js";

  let { account = null, initialData = null, onSaved = () => {}, onDismiss = () => {} } = $props();

  let isEdit = $derived(account !== null);

  // Capture initial values from the `account` (edit) or `initialData` (new with prefill) prop.
  // Form fields are intentionally $state (not $derived) — the user
  // edits them and we do NOT re-initialize on prop changes.
  // svelte-ignore state_referenced_locally
  const _init = account || initialData || {};
  let email = $state(_init.email || _init.retposto || "");
  let name = $state(_init.name || _init.nomo || "");
  let password = $state("");
  let imapServer = $state(_init.imap_server || _init.imap_servilo || "");
  let smtpServer = $state(_init.smtp_server || _init.smtp_servilo || "");
  let saving = $state(false);
  let error = $state("");

  async function handleSave() {
    if (!email.trim()) {
      error = "Email address is required.";
      return;
    }
    saving = true;
    error = "";
    try {
      if (isEdit) {
        const updates = {};
        if (name.trim()) updates.name = name.trim();
        if (imapServer.trim()) updates.imap_server = imapServer.trim();
        if (smtpServer.trim()) updates.smtp_server = smtpServer.trim();
        if (password) updates.password = password;
        await emailApi.updateAccount(account.uuid, updates);
      } else {
        await emailApi.createAccount({
          email: email.trim(),
          password: password,
          name: name.trim(),
          imap_server: imapServer.trim(),
          smtp_server: smtpServer.trim(),
        });
      }
      onSaved();
    } catch (err) {
      error = err.message || "Failed to save account.";
    } finally {
      saving = false;
    }
  }
</script>

<div class="modal-overlay" onclick={onDismiss} onkeydown={(e) => e.key === "Escape" && onDismiss()} role="button" tabindex="-1" aria-label="Dismiss">
  <div class="modal" onclick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" tabindex="0" onkeydown={() => {}}>
    <div class="modal-header">
      <h2>{isEdit ? "Edit Email Account" : "Add Email Account"}</h2>
      <p class="subtitle">{isEdit ? `Editing "${account.email || account.retposto}"` : "Configure a new email account"}</p>
    </div>
    <div class="form">
      <label class="field">
        <span class="field-label">Email Address</span>
        <!-- svelte-ignore a11y_autofocus -->
        <input type="email" class="text-input" bind:value={email} placeholder="user@example.com" disabled={isEdit} autofocus />
      </label>
      <label class="field">
        <span class="field-label">Display Name</span>
        <input type="text" class="text-input" bind:value={name} placeholder="Your Name" />
      </label>
      <label class="field">
        <span class="field-label">Password</span>
        <input type="password" class="text-input" bind:value={password} placeholder={isEdit ? "Leave blank to keep current" : "Required"} />
      </label>
      <label class="field">
        <span class="field-label">IMAP Server</span>
        <input type="text" class="text-input" bind:value={imapServer} placeholder="Auto-detected if empty" />
      </label>
      <label class="field">
        <span class="field-label">SMTP Server</span>
        <input type="text" class="text-input" bind:value={smtpServer} placeholder="Auto-detected if empty" />
      </label>
      {#if error}
        <p class="error">{error}</p>
      {/if}
      <div class="form-actions">
        <button class="btn-primary" onclick={handleSave} disabled={saving || !email.trim() || (!isEdit && !password)}>
          {saving ? "Saving…" : isEdit ? "Update" : "Add Account"}
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
