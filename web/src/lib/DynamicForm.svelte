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
  import PreviewDialog from "./PreviewDialog.svelte";
  import { createPreviewState } from "./preview.svelte.js";
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

  // ── Preview state ────────────────────────────────────────────────────
  let preview = $state(createPreviewState());

  /** Open preview for the given content and format. */
  function openPreview(content, format = "markdown", title = "Preview") {
    preview.show(content, format, title);
  }

  // ── Field grouping for inline layout ──────────────────────────────────
  /**
   * Build a flat ordered list of all fields (params first, then flags).
   * Each entry: { type: "param"|"flag", def: {…} }
   */
  let allFields = $derived.by(() => {
    const fields = [];
    for (const p of params) fields.push({ type: "param", def: p });
    for (const f of flags) fields.push({ type: "flag", def: f });
    return fields;
  });

  /**
   * Group consecutive fields into rows.
   * Fields with explicit width (e.g. "50%") that are NOT multiline
   * are grouped into inline rows. All others get their own row.
   */
  let renderedGroups = $derived.by(() => {
    const groups = [];
    let currentInline = [];

    function flushInline() {
      if (currentInline.length > 0) {
        groups.push({ inline: true, fields: [...currentInline] });
        currentInline = [];
      }
    }

    for (const field of allFields) {
      const w = field.def.width || "";
      const isMultiline = field.def.multiline;
      // Inline = has width < 100%, not multiline, not a uuid field
      const hasExplicitWidth = w !== "" && w !== "100%";
      const shouldInline = hasExplicitWidth && !isMultiline
        && field.def.type !== "uuid" && !field.def.uuidSource;

      if (shouldInline) {
        currentInline.push(field);
      } else {
        flushInline();
        groups.push({ inline: false, fields: [field] });
      }
    }
    flushInline();
    return groups;
  });

  /** Extract numeric flex value from a width string like "50%" or "1fr" */
  function flexWidth(width) {
    if (!width || width === "100%") return "1";
    if (width.endsWith("%")) return width.replace("%", "");
    return width;
  }

  // ── Autocomplete data loading ─────────────────────────────────────────
  let autocompleteData = $state({}); // {fieldName: [values]}

  $effect(() => {
    // Collect unique autocompleteSource values from params + flags
    const sources = new Set();
    for (const p of (node?.params || [])) {
      if (p.autocompleteSource) sources.add(p.autocompleteSource);
    }
    for (const f of (node?.flags || [])) {
      if (f.autocompleteSource) sources.add(f.autocompleteSource);
    }
    if (sources.size === 0) return;

    for (const src of sources) {
      if (src === "contact/org") {
        _fetchAutocompleteData("/api/v1/contacts/autocomplete/organization", src);
      } else if (src === "email/account") {
        _fetchAutocompleteData("/api/v1/email/autocomplete/account", src);
      }
    }
  });

  async function _fetchAutocompleteData(url, sourceKey) {
    try {
      const resp = await fetch(url);
      if (!resp.ok) return;
      const data = await resp.json();
      const values = data.values || data;
      autocompleteData = { ...autocompleteData, [sourceKey]: values };
    } catch {
      // silently fail — autocomplete is a nice-to-have
    }
  }

  function _getAutocompleteOptions(fieldDef) {
    if (!fieldDef.autocompleteSource) return [];
    return autocompleteData[fieldDef.autocompleteSource] || [];
  }

  function handleKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      handleSubmit(e);
    }
    // Ctrl+Shift+P — preview the first multiline/text field's content
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === "p" || e.key === "P")) {
      e.preventDefault();
      // Find first multiline/text field with content and preview it
      for (const field of allFields) {
        const val = fieldValues[field.def.name];
        if (val && typeof val === "string" && val.trim()) {
          const isLongText = field.def.multiline || (val && val.length > 100);
          if (isLongText) {
            const fmt = fieldValues["format"] || fieldValues["body-format"] || fieldValues["body_format"] || "markdown";
            openPreview(val, fmt, "Preview: " + field.def.name);
            break;
          }
        }
      }
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<form onsubmit={handleSubmit} class="dynamic-form">
  <h3 class="form-title">{formTitle}</h3>

  {#each renderedGroups as group}
    {#if group.inline}
      <div class="field-row">
        {#each group.fields as field}
          {@const fd = field.def}
          {@const val = fieldValues[fd.name]}
          {@const isMultiline = fd.multiline}
          <div class="field-cell" style="flex:{flexWidth(fd.width)}">
            <FormField
              label={fd.name}
              hint={fd.placeholder || fd.help || ""}
              required={fd.required}
              error={formErrors[fd.name] || ""}
            >
              {#snippet children()}
                {#if field.type === "flag" && fd.type === "flag"}
                  <label class="checkbox-label">
                    <input type="checkbox" class="df-checkbox"
                      checked={!!val}
                      onchange={(e) => setField(fd.name, e.target.checked)} />
                    <span class="checkbox-text">{fd.help || "Enable"}</span>
                  </label>
                {:else if fd.uuidSource}
                  <UuidPicker uuidSource={fd.uuidSource} value={val || ""}
                    placeholder={fd.help || `Select ${fd.name}`}
                    required={fd.required}
                    onchange={(v) => setField(fd.name, v)} />
                {:else if field.type === "flag" && fd.values && fd.values.length > 0}
                  <select id={fd.name} class="df-input"
                    value={val || ""}
                    onchange={(e) => setField(fd.name, e.target.value)}>
                    <option value="">— Select {fd.name} —</option>
                    {#each fd.values as opt}
                      <option value={opt}>{opt}</option>
                    {/each}
                  </select>
                {:else}
                  <input id={fd.name} type={fieldType(fd)} class="df-input"
                    value={val || ""}
                    oninput={(e) => setField(fd.name, e.target.value)}
                    placeholder={fd.help || fd.placeholder || ""} />
                {/if}
              {/snippet}
            </FormField>
          </div>
        {/each}
      </div>
    {:else}
      {@const fd = group.fields[0].def}
      {@const field = group.fields[0]}
      {@const val = fieldValues[fd.name] || ""}
      {@const acOptions = _getAutocompleteOptions(fd)}
      {@const isMultiline = fd.multiline}
      <FormField
        label={fd.name}
        hint={fd.placeholder || fd.help || ""}
        required={fd.required}
        error={formErrors[fd.name] || ""}
      >
        {#snippet children()}
          {#if fd.type === "uuid" || fd.uuidSource}
            <UuidPicker
              uuidSource={fd.uuidSource || ""}
              value={val}
              placeholder={fd.placeholder || `Enter ${fd.name}`}
              required={fd.required}
              onchange={(v) => setField(fd.name, v)}
            />
          {:else if field.type === "flag" && fd.type === "flag"}
            <label class="checkbox-label">
              <input type="checkbox" class="df-checkbox"
                checked={!!val}
                onchange={(e) => setField(fd.name, e.target.checked)} />
              <span class="checkbox-text">{fd.help || "Enable"}</span>
            </label>
          {:else if fd.uuidSource}
            <UuidPicker uuidSource={fd.uuidSource} value={val || ""}
              placeholder={fd.help || `Select ${fd.name}`}
              required={fd.required}
              onchange={(v) => setField(fd.name, v)} />
          {:else if field.type === "flag" && fd.values && fd.values.length > 0}
            <select id={fd.name} class="df-input"
              value={val || ""}
              onchange={(e) => setField(fd.name, e.target.value)}>
              <option value="">— Select {fd.name} —</option>
              {#each fd.values as opt}
                <option value={opt}>{opt}</option>
              {/each}
            </select>
          {:else if fd.type === "datetime"}
            <input id={fd.name} type="datetime-local" class="df-input"
              value={val} oninput={(e) => setField(fd.name, e.target.value)}
              required={fd.required} placeholder={fd.placeholder || ""} />
          {:else if fd.type === "date"}
            <input id={fd.name} type="date" class="df-input"
              value={val} oninput={(e) => setField(fd.name, e.target.value)}
              required={fd.required} />
          {:else if fd.type === "number"}
            <input id={fd.name} type="number" class="df-input"
              value={val} oninput={(e) => setField(fd.name, e.target.value)}
              required={fd.required} placeholder={fd.placeholder || ""} />
          {:else if isMultiline}
            <div class="multiline-wrap">
              <textarea id={fd.name} class="df-textarea"
                value={val} oninput={(e) => setField(fd.name, e.target.value)}
                required={fd.required} placeholder={fd.placeholder || fd.help || ""}
                rows="8"></textarea>
              <div class="multiline-tools">
                <button type="button" class="preview-btn"
                  onclick={() => {
                    const fmt = fieldValues["format"] || fieldValues["body-format"] || "markdown";
                    openPreview(fieldValues[fd.name] || "", fmt, "Preview: " + fd.name);
                  }}
                  disabled={!fieldValues[fd.name] || !fieldValues[fd.name].trim()}
                  title="Preview (Ctrl+Shift+P)">Preview <kbd>Ctrl+Shift+P</kbd></button>
              </div>
            </div>
          {:else if isSensitive(fd.name)}
            <input id={fd.name} type="password" class="df-input"
              value={val} oninput={(e) => setField(fd.name, e.target.value)}
              required={fd.required} placeholder={fd.placeholder || ""} />
          {:else}
            <input id={fd.name} type={fieldType(fd)} class="df-input"
              value={val} oninput={(e) => setField(fd.name, e.target.value)}
              required={fd.required} placeholder={fd.placeholder || fd.help || ""}
              list={fd.autocompleteSource ? `${fd.name}-list` : undefined} />
            <datalist id={`${fd.name}-list`}>
              {#each acOptions as opt}
                <option value={opt}></option>
              {/each}
            </datalist>
          {/if}
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

{#if preview.showing}
  <PreviewDialog
    showing={preview.showing}
    htmlContent={preview.htmlContent}
    title={preview.title}
    onclose={() => preview.close()}
  />
{/if}

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
  .field-row {
    display: flex;
    gap: 0.75rem;
    align-items: flex-start;
  }
  .field-cell {
    min-width: 0;
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
  :global(.df-textarea) {
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
    resize: vertical;
    min-height: 120px;
  }
  :global(.df-textarea:focus) {
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
  .multiline-wrap {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .multiline-tools {
    display: flex;
    justify-content: flex-end;
  }
  .preview-btn {
    padding: 0.25rem 0.5rem;
    border: 1px solid #444;
    border-radius: 4px;
    background: transparent;
    color: #b0b0c0;
    font-family: monospace;
    font-size: 0.72rem;
    cursor: pointer;
    transition: background 0.1s, color 0.1s;
    white-space: nowrap;
  }
  .preview-btn:hover:not(:disabled) {
    background: #2a2a44;
    color: #e0e0e0;
  }
  .preview-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
</style>
