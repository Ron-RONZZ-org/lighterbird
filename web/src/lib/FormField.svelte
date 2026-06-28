<script>
  /**
   * FormField.svelte — Unified form field wrapper.
   *
   * Provides consistent styling for input, select, textarea, and
   * checkbox-type fields used throughout lighterbird form components.
   *
   * Props:
   *   label      — field label text
   *   hint       — optional hint text shown next to label
   *   error      — optional error message
   *   required   — if true, shows indicator
   *   id         — input id (auto-generated from label if omitted)
   */
  let {
    label = "",
    hint = "",
    error = "",
    required = false,
    id = label ? label.toLowerCase().replace(/\s+/g, "-") : "",
    class: className = "",
    children,
  } = $props();
</script>

<div class="field {className}" class:has-error={!!error}>
  {#if label}
    <label for={id}>
      <span class="field-label">{label}</span>
      {#if required}
        <span class="required-badge">required</span>
      {/if}
      {#if hint}
        <span class="field-hint">{hint}</span>
      {/if}
    </label>
  {/if}
  {@render children?.()}
  {#if error}
    <p class="field-error">{error}</p>
  {/if}
</div>

{#snippet formActions()}
  <div class="form-actions">
    {@render children?.()}
  </div>
{/snippet}

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  .field.has-error :global(input),
  .field.has-error :global(select),
  .field.has-error :global(textarea) {
    border-color: #8a4a4a;
  }
  label {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    flex-wrap: wrap;
  }
  .field-label {
    font-size: 0.78rem;
    color: var(--clr-sub);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .field-hint {
    font-weight: 400;
    text-transform: none;
    letter-spacing: 0;
    color: var(--clr-dim);
    font-size: 0.7rem;
  }
  .required-badge {
    display: inline-block;
    font-size: 0.55rem;
    text-transform: uppercase;
    background: #5b2020;
    color: #e0a0a0;
    padding: 0.08rem 0.4rem;
    border-radius: 3px;
    font-weight: 600;
    vertical-align: middle;
  }
  .field-error {
    color: #aa6a6a;
    font-size: 0.78rem;
    margin: 0;
  }
  :global(.form-actions) {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
    margin-top: 0.25rem;
  }
  :global(.form-actions button) {
    padding: 0.45rem 1rem;
    border-radius: 6px;
    border: 1px solid #444;
    font-family: monospace;
    font-size: 0.85rem;
    cursor: pointer;
    transition: background 0.1s, opacity 0.1s;
  }
  :global(.form-actions .btn-primary) {
    background: #0f3460;
    color: #e0e0e0;
    border-color: #4a6a9a;
  }
  :global(.form-actions .btn-primary:hover:not(:disabled)) {
    background: #1a4a7a;
  }
  :global(.form-actions .btn-secondary) {
    background: #2a2a3e;
    color: #b0b0c0;
  }
  :global(.form-actions .btn-secondary:hover) {
    background: #3a3a5a;
  }
  :global(.form-actions button:disabled) {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
