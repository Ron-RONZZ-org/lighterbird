<script>
  import { tabStore } from "./tabStore.svelte.js";
  import { sieve as sieveApi } from "./api.js";

  let { data = {} } = $props();
  let existingScript = $derived(data?.script || null);
  let isNew = $derived(!existingScript);

  let name = $state(existingScript?.name || "");
  let content = $state(existingScript?.content || "");
  let validationResult = $state(null);
  let saving = $state(false);

  let isSystem = $derived(existingScript?.system || false);
  let placeholder = 'require ["fileinto"];\nif anyof (header :contains "Subject" "newsletter") {\n  fileinto "Newsletters";\n}';

  async function handleValidate() {
    try {
      const result = await sieveApi.validate(content);
      validationResult = result;
    } catch (err) {
      validationResult = { is_valid: false, error: err.message };
    }
  }

  async function handleSave() {
    saving = true;
    try {
      if (isNew) {
        await sieveApi.create({ name, content });
      } else {
        await sieveApi.update(existingScript.name, {
          name: name !== existingScript.name ? name : undefined,
          content: content !== existingScript.content ? content : undefined,
        });
      }
      tabStore.close(tabStore.active.id);
      // Re-fetch the list tab if it's open
      for (const t of tabStore.tabs) {
        if (t.type === "sieve-list") {
          tabStore.setActive(t.id);
          try {
            const result = await sieveApi.list({});
            tabStore.update(t.id, result);
          } catch { /* silent */ }
          break;
        }
      }
    } catch (err) {
      validationResult = { is_valid: false, error: err.message || "Save failed" };
    } finally {
      saving = false;
    }
  }

  function handleCancel() {
    tabStore.close(tabStore.active.id);
  }
</script>

<div class="sieve-editor">
  <div class="header">
    <h2>{isNew ? "New Sieve Script" : `Edit: ${existingScript.name}`}</h2>
    {#if !isNew}
      <p class="subtitle">Global script — activate per-account via !email sieve activate</p>
    {/if}
  </div>

  {#if isSystem}
    <div class="notice">System scripts are read-only.</div>
  {/if}

  <div class="form">
    <div class="field">
      <label for="sieve-name">Name</label>
      <input
        id="sieve-name"
        type="text"
        bind:value={name}
        disabled={!isNew && !isSystem}
        placeholder="my-filter"
      />
    </div>

    <div class="field content-field">
      <label for="sieve-content">Sieve Script Content</label>
      <textarea
        id="sieve-content"
        bind:value={content}
        disabled={isSystem}
        {placeholder}
        rows="15"
        spellcheck="false"
      ></textarea>
    </div>

    {#if validationResult}
      <div class="validation" class:error={!validationResult.is_valid}>
        {#if validationResult.is_valid}
          ✓ Syntax OK
        {:else}
          ✗ {validationResult.error}
        {/if}
      </div>
    {/if}
  </div>

  <div class="actions">
    {#if !isSystem}
      <button class="btn" onclick={handleValidate} disabled={!content.trim()}>Validate</button>
      <button class="btn primary" onclick={handleSave} disabled={saving || !name.trim() || isSystem}>
        {saving ? "Saving…" : "Save"}
      </button>
    {/if}
    <button class="btn" onclick={handleCancel}>Cancel</button>
  </div>
</div>

<style>
  .sieve-editor {
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: 1rem;
    background: #1a1a2e;
    font-family: monospace;
    font-size: 0.85rem;
    overflow-y: auto;
  }
  .header h2 {
    margin: 0 0 0.2rem 0;
    font-size: 1rem;
    color: #e0e0e0;
  }
  .subtitle {
    margin: 0 0 0.8rem 0;
    color: var(--clr-muted);
    font-size: 0.75rem;
  }
  .notice {
    background: #2a2a1e;
    border: 1px solid #5a5a2a;
    color: #dba87f;
    padding: 0.4rem 0.7rem;
    border-radius: 3px;
    margin-bottom: 1rem;
    font-size: 0.8rem;
  }
  .form {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.7rem;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .field label {
    color: #7c7c9a;
    font-size: 0.78rem;
  }
  .field input[type="text"] {
    padding: 0.3rem 0.5rem;
    border: 1px solid #4a4a6a;
    border-radius: 3px;
    background: #2a2a44;
    color: #e0e0e0;
    font-family: monospace;
    font-size: 0.85rem;
  }
  .field input:disabled,
  .field textarea:disabled {
    opacity: 0.6;
  }
  .content-field textarea {
    padding: 0.5rem;
    border: 1px solid #4a4a6a;
    border-radius: 3px;
    background: #12121e;
    color: #ccc;
    font-family: monospace;
    font-size: 0.82rem;
    line-height: 1.5;
    resize: vertical;
    min-height: 200px;
    tab-size: 2;
  }
  .content-field textarea:focus {
    outline: none;
    border-color: #6a6a9a;
  }
  .validation {
    padding: 0.4rem 0.7rem;
    border-radius: 3px;
    font-size: 0.8rem;
  }
  .validation.error {
    background: #2a1a1a;
    border: 1px solid #6a2a2a;
    color: #e07070;
  }
  .validation:not(.error) {
    background: #1a2a1a;
    border: 1px solid #2a5a2a;
    color: #7fdb7f;
  }
  .actions {
    display: flex;
    gap: 0.5rem;
    padding-top: 1rem;
    border-top: 1px solid #2a2a3e;
    margin-top: 0.5rem;
    flex-shrink: 0;
  }
  .btn {
    padding: 0.35rem 0.8rem;
    border: 1px solid #4a4a6a;
    border-radius: 3px;
    background: #2a2a44;
    color: #ccc;
    font-family: monospace;
    font-size: 0.85rem;
    cursor: pointer;
  }
  .btn:hover { background: #3a3a5a; }
  .btn.primary { background: #3a5a8a; border-color: #4a6a9a; color: #e0e0e0; }
  .btn.primary:hover { background: #4a6a9a; }
  .btn:disabled { opacity: 0.5; cursor: default; }
</style>
