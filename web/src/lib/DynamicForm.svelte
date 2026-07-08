<script>
  /**
   * DynamicForm.svelte — Generic command form rendered from tree metadata.
   *
   * Given a command path (e.g. ["contacts", "add"]), it looks up the
   * node from commandTree and renders form fields for each param and flag.
   *
   * Supports: string, number, date, datetime, uuid (with UuidPicker), flag, email, password
   *
   * Password-type flags are detected via a "sensitive" metadata field in tree.py.
   * The frontend detects this via the flag name (those containing "password" or "secret").
   *
   * Props:
   *   commandPath   — token path for the command, e.g. ["email", "account", "add"]
   *   commandPrefix — the root command name, e.g. "email.account.add" (used for submit)
   *   initialData   — pre-filled values from typed args
   *   onsubmit      — called with {tokens, flags, remaining}
   */

  import { findNode, commandTree } from "./commandTree.js";
  import FormField from "./FormField.svelte";
  import UuidPicker from "./UuidPicker.svelte";

  let {
    commandPath = [],
    initialData = {},
    onsubmit = async () => {},
    onDirtyChange = () => {},
  } = $props();

  let node = $derived(findNode(commandPath));
  let params = $derived(node?.params || []);
  let flags = $derived(node?.flags || []);
  let submitting = $state(false);
  let formErrors = $state({});

  // ── Build reactive form values from initial data ──────────────────────
  let fieldValues = $state({});
  let dirty = $state(false);

  // Initialize form fields from initialData + tree metadata
  $effect(() => {
    const vals = { ...initialData };
    for (const p of (node?.params || [])) {
      if (!(p.name in vals)) vals[p.name] = "";
    }
    for (const f of (node?.flags || [])) {
      if (f.type === "flag") {
        vals[f.name] = initialData[f.name] || false;
      } else if (!(f.name in vals)) {
        vals[f.name] = "";
      }
    }
    fieldValues = vals;
  });

  // Dirty tracking — derived synchronously from current values
  $effect(() => {
    const vals = fieldValues;
    if (Object.keys(vals).length === 0) { dirty = false; return; }
    let isDirty = false;
    for (const key of Object.keys(vals)) {
      const cur = vals[key];
      const init = initialData[key];
      const curStr = typeof cur === "boolean" ? String(cur) : cur ?? "";
      const initStr = typeof init === "boolean" ? String(init) : init ?? "";
      if (curStr !== initStr) { isDirty = true; break; }
    }
    dirty = isDirty;
  });

  // Notify parent — de-aliased via setTimeout to prevent reactive cascading
  let _lastDirty = $state(false);
  $effect(() => {
    if (dirty !== _lastDirty) {
      _lastDirty = dirty;
      setTimeout(() => onDirtyChange(dirty), 0);
    }
  });

  function setField(name, val) {
    fieldValues = { ...fieldValues, [name]: val };
    if (formErrors[name]) {
      const next = { ...formErrors };
      delete next[name];
      formErrors = next;
    }
  }

  function isSensitive(name) {
    return /password|secret|key|token/i.test(name);
  }

  function fieldType(flagDef) {
    if (flagDef.type === "number") return "number";
    if (flagDef.type === "date") return "date";
    if (flagDef.type === "datetime") return "datetime-local";
    if (flagDef.type === "flag") return "checkbox";
    if (isSensitive(flagDef.name)) return "password";
    return "text";
  }

  async function handleSubmit(e) {
    e.preventDefault();
    const errors = {};
    const flags_out = {};
    let remaining = [];

    // Build positional args
    for (let i = 0; i < params.length; i++) {
      const p = params[i];
      const val = (fieldValues[p.name] || "").trim();
      if (p.required && !val) {
        errors[p.name] = `${p.name} is required`;
      }
      remaining.push(val);
    }

    // Build flags
    for (const f of flags) {
      let val = fieldValues[f.name];
      if (f.type === "flag") {
        if (val) flags_out[f.name] = "true";
      } else if (f.type === "number") {
        if (val !== "" && val !== undefined && val !== null) {
          if (isNaN(Number(val))) {
            errors[f.name] = `${f.name} must be a number`;
          } else {
            flags_out[f.name] = String(val);
          }
        }
      } else {
        if (val && typeof val === "string" && val.trim()) {
          flags_out[f.name] = val.trim();
        }
      }
    }

    if (Object.keys(errors).length > 0) {
      formErrors = errors;
      return;
    }

    submitting = true;
    formErrors = {};
    try {
      await onsubmit({
        tokens: commandPath,
        flags: flags_out,
        remaining,
      });
    } finally {
      submitting = false;
    }
  }

  let formTitle = $derived(
    commandPath
      .join(" ")
      .replace(/\b\w/g, (c) => c.toUpperCase()),
  );

  function handleKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      handleSubmit(e);
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<form onsubmit={handleSubmit} class="dynamic-form">
  <h3 class="form-title">{formTitle}</h3>

  {#each params as param}
    {@const val = fieldValues[param.name] || ""}
    <FormField
      label={param.name}
      hint={param.placeholder || ""}
      required={param.required}
      error={formErrors[param.name] || ""}
    >
      {#snippet children()}
        {#if param.type === "uuid" || param.uuidSource}
          <UuidPicker
            uuidSource={param.uuidSource || ""}
            value={val}
            placeholder={param.placeholder || `Enter ${param.name}`}
            required={param.required}
            onchange={(v) => setField(param.name, v)}
          />
        {:else if param.type === "datetime"}
          <input
            id={param.name}
            type="datetime-local"
            class="df-input"
            value={val}
            oninput={(e) => setField(param.name, e.target.value)}
            required={param.required}
            placeholder={param.placeholder || ""}
          />
        {:else if param.type === "date"}
          <input
            id={param.name}
            type="date"
            class="df-input"
            value={val}
            oninput={(e) => setField(param.name, e.target.value)}
            required={param.required}
          />
        {:else if param.type === "number"}
          <input
            id={param.name}
            type="number"
            class="df-input"
            value={val}
            oninput={(e) => setField(param.name, e.target.value)}
            required={param.required}
            placeholder={param.placeholder || ""}
          />
        {:else if isSensitive(param.name)}
          <input
            id={param.name}
            type="password"
            class="df-input"
            value={val}
            oninput={(e) => setField(param.name, e.target.value)}
            required={param.required}
            placeholder={param.placeholder || ""}
          />
        {:else}
          <input
            id={param.name}
            type="text"
            class="df-input"
            value={val}
            oninput={(e) => setField(param.name, e.target.value)}
            required={param.required}
            placeholder={param.placeholder || ""}
          />
        {/if}
      {/snippet}
    </FormField>
  {/each}

  {#each flags as flag}
    {@const val = fieldValues[flag.name]}
    {#if flag.type === "flag"}
      <FormField label={flag.name} hint={flag.help || ""}>
        {#snippet children()}
          <label class="checkbox-label">
            <input
              type="checkbox"
              class="df-checkbox"
              checked={!!val}
              onchange={(e) => setField(flag.name, e.target.checked)}
            />
            <span class="checkbox-text">{flag.help || "Enable"}</span>
          </label>
        {/snippet}
      </FormField>
    {:else if flag.uuidSource}
      <FormField label={flag.name} hint={flag.help || ""} required={flag.required}>
        {#snippet children()}
          <UuidPicker
            uuidSource={flag.uuidSource}
            value={val || ""}
            placeholder={flag.help || `Select ${flag.name}`}
            required={flag.required}
            onchange={(v) => setField(flag.name, v)}
          />
        {/snippet}
      </FormField>
    {:else}
      <FormField label={flag.name} hint={flag.help || ""} required={flag.required}
        error={formErrors[flag.name] || ""}>
        {#snippet children()}
          <input
            id={flag.name}
            type={fieldType(flag)}
            class="df-input"
            value={val || ""}
            oninput={(e) => setField(flag.name, e.target.value)}
            placeholder={flag.help || ""}
          />
        {/snippet}
      </FormField>
    {/if}
  {/each}

  <div class="form-actions">
    <button type="submit" class="btn-primary" disabled={submitting}>
      {submitting ? "Saving…" : "Save"}
    </button>
  </div>
</form>

<style>
  .dynamic-form {
    padding: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .form-title {
    margin: 0 0 0.25rem;
    font-size: 0.95rem;
    color: #e0e0e0;
    font-weight: 600;
    font-family: monospace;
  }
  :global(.df-input) {
    width: 100%;
    padding: 0.5rem 0.6rem;
    background: #16213e;
    border: 1px solid #333;
    color: #e0e0e0;
    border-radius: 4px;
    font-family: inherit;
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.15s;
    box-sizing: border-box;
  }
  :global(.df-input:focus) {
    border-color: #5a5a8a;
  }
  :global(.df-checkbox) {
    width: 1.1rem;
    height: 1.1rem;
    accent-color: #4a6fa5;
  }
  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
  }
  .checkbox-text {
    font-size: 0.85rem;
    color: #ccc;
  }
</style>
