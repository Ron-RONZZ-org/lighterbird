<script>
  /** Todo creation form — supports templates, parent/dependency, file attachment. */

  import { onMount } from "svelte";
  import { todo as todoApi, drafts as draftsApi } from "./api.js";
  import TemplateFieldInput from "./TemplateFieldInput.svelte";
  import { createCowrite, CowriteButton, CowritePanel } from "@lightercore/ui/cowrite/index.js";
  import MultiEntryField from "./MultiEntryField.svelte";

  let { initialData = {}, onsubmit, onDirtyChange = () => {} } = $props();
  // svelte-ignore state_referenced_locally
  const _initial = initialData;

  let title = $state(_initial.title || "");
  let description = $state(_initial.description || "");
  let priority = $state(_initial.priority || "5");
  let due = $state(_initial.due || "");
  let parentUuid = $state(_initial.parent_uuid || "");
  let dependencyUuids = $state([]);
  let tags = $state(_initial.tags || []);
  let filePaths = $state([]);
  let adding = $state(false);
  let savingDraft = $state(false);
  let draftSaved = $state(false);
  let draftUuid = $state(_initial._draft_uuid || null);

  // ── LLM co-writing ─────────────────────────────────────────────────
  let cowrite = $state(createCowrite({
    formType: "todo-add",
    getCurrentContent: () => ({ title, description }),
    applyEdit: (field, t) => {
      if (field === "title") title = t;
      else if (field === "description") description = t;
    },
  }));

  /** Save draft on Ctrl+S */
  async function saveDraft() {
    if (savingDraft) return;
    savingDraft = true;
    draftSaved = false;
    try {
      const result = await draftsApi.save(
        "todo",
        title || "(untitled)",
        { title, description, priority, due, parent_uuid: parentUuid, template: selectedTemplate, tags: tags.join(",") },
        draftUuid,
      );
      draftUuid = result.uuid;
      draftSaved = true;
      setTimeout(() => { draftSaved = false; }, 2000);
    } catch { /* silent */ }
    finally { savingDraft = false; }
  }

  function handleFormKeydown(e) {
    if ((e.ctrlKey || e.metaKey) && e.key === "s") {
      e.preventDefault();
      saveDraft();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  // Template support
  let templates = $state([]);
  let selectedTemplate = $state(_initial.template || "");
  let templateFields = $state([]);
  let templateValues = $state({});
  let loadingTemplates = $state(false);

  // Dirty state — compare current against initial
  /** @param {object} a @param {object} b */
  function shallowDiff(a, b) {
    if (Object.keys(a).length !== Object.keys(b).length) return true;
    for (const k of Object.keys(a)) {
      if (a[k] !== b[k]) return true;
    }
    return false;
  }
  let dirty = $derived(
    title !== (_initial.title || "")
    || description !== (_initial.description || "")
    || priority !== (_initial.priority || "5")
    || due !== (_initial.due || "")
    || parentUuid !== (_initial.parent_uuid || "")
    || dependencyUuids.length > 0
    || tags.length > 0
    || filePaths.length > 0
    || selectedTemplate !== (_initial.template || "")
    || shallowDiff(templateValues, {})
  );
  $effect(() => { onDirtyChange(dirty); });

  // Autocomplete for parent
  let parentSuggestions = $state([]);
  let showParentSuggestions = $state(false);

  // Load templates on mount
  onMount(() => {
    loadTemplates();
  });

  async function loadTemplates() {
    loadingTemplates = true;
    try {
      const result = await todoApi.listTemplates();
      templates = result.templates || [];
    } catch {
      templates = [];
    } finally {
      loadingTemplates = false;
    }
  }

  async function onTemplateChange(tplName) {
    selectedTemplate = tplName;
    if (!tplName) {
      templateFields = [];
      templateValues = {};
      return;
    }
    try {
      const tpl = await todoApi.getTemplate(tplName);
      if (tpl) {
        templateFields = tpl.fields || [];
        templateValues = {};
        if (tpl.title_placeholder && !title) {
          title = tpl.title_placeholder;
        }
      }
    } catch {
      templateFields = [];
    }
  }

  async function searchParentTitle(q) {
    if (!q || q.length < 2) { parentSuggestions = []; showParentSuggestions = false; return; }
    try {
      const result = await todoApi.searchTitles(q);
      parentSuggestions = result.results || [];
      showParentSuggestions = parentSuggestions.length > 0;
    } catch {
      parentSuggestions = [];
    }
  }

  async function searchDepTitle(q) {
    if (!q || q.length < 2) return [];
    try {
      const result = await todoApi.searchTitles(q);
      return (result.results || []).map((item) => ({
        label: item.title,
        value: item.uuid,
      }));
    } catch {
      return [];
    }
  }

  function selectParent(item) {
    parentUuid = item.uuid;
    parentSuggestions = [];
    showParentSuggestions = false;
  }

  function highlightMatch(text, query) {
    if (!query) return text;
    const idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx === -1) return text;
    return text.slice(0, idx) + '<mark>' + text.slice(idx, idx + query.length) + '</mark>' + text.slice(idx + query.length);
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!title) return;
    adding = true;
    try {
      const flags = { priority };
      if (due) flags.due = due;
      if (description) flags.description = description;
      if (parentUuid) flags.parent = parentUuid;
      if (dependencyUuids.length > 0) flags.dependency = dependencyUuids.join(",");
      if (tags.length > 0) flags.tags = tags.join(",");
      if (filePaths.length > 0) flags.file = filePaths.join(",");
      if (selectedTemplate) {
        flags.template = selectedTemplate;
        // Add template field values as --text name:value flags
        for (const [key, val] of Object.entries(templateValues)) {
          if (val) {
            flags[`text_${key}`] = `${key}:${val}`;
          }
        }
      }
      await onsubmit({
        tokens: ["todo", "add"],
        flags,
        remaining: [title],
      });
      onDirtyChange(false);
    } finally {
      adding = false;
    }
  }
</script>

<form onsubmit={handleSubmit} class="todo-add-form">
  <!-- Toolbar -->
  <div class="form-toolbar">
    <div class="toolbar-left">
      <span class="toolbar-title">Add Todo</span>
    </div>
    <div class="toolbar-right">
      <CowriteButton {cowrite} />
    </div>
  </div>

  <!-- Template selector (first field) -->
  <div class="field">
    <label for="template">Template <span class="field-hint">(optional — changes available fields)</span></label>
    <select id="template" value={selectedTemplate}
      onchange={(e) => onTemplateChange(e.target.value)}>
      <option value="">— No template —</option>
      {#each templates as tpl}
        <option value={tpl.nomo}>{tpl.nomo}</option>
      {/each}
    </select>
  </div>

  <div class="field">
    <label for="title">Title</label>
    <input id="title" type="text" bind:value={title} required placeholder="What needs to be done?" />
  </div>

  <div class="field">
    <label for="description">Description</label>
    <textarea id="description" bind:value={description} rows="4" placeholder="Optional details..."></textarea>
  </div>

  <!-- Template-specific fields -->
  {#if templateFields.length > 0}
    <div class="template-fields">
      <h4>Template Fields</h4>
      {#each templateFields as field}
        <div class="field">
          <label for="tpl-{field.kampo_nomo}">
            {field.kampo_nomo}
            {#if field.estas_deviga}
              <span class="required-badge">required</span>
            {/if}
          </label>
          <TemplateFieldInput
            {field}
            value={templateValues[field.kampo_nomo] || ''}
            onchange={(v) => { templateValues[field.kampo_nomo] = v; }}
          />
        </div>
      {/each}
    </div>
  {/if}

  <div class="row-fields">
    <div class="field">
      <label for="priority">Priority (1-10)</label>
      <input id="priority" type="number" bind:value={priority} min="1" max="10" />
    </div>
    <div class="field">
      <label for="due">Due Date</label>
      <input id="due" type="date" bind:value={due} />
    </div>
  </div>

  <!-- Parent (subtask) with autocomplete -->
  <div class="field autocomplete-field">
    <label for="parent">Parent UUID <span class="field-hint">(subtask of)</span></label>
    <div class="autocomplete-wrapper">
      <input id="parent" type="text" bind:value={parentUuid}
        placeholder="Search by title or enter UUID (comma-separated)"
        onfocus={() => { if (parentSuggestions.length > 0) showParentSuggestions = true; }}
        onblur={() => setTimeout(() => showParentSuggestions = false, 200)} />
      {#if showParentSuggestions && parentSuggestions.length > 0}
        <div class="autocomplete-dropdown">
          {#each parentSuggestions as item}
            <div class="autocomplete-item" onmousedown={() => selectParent(item)} onkeydown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectParent(item); } }} role="button" tabindex="-1">
              <span class="ac-uuid">{item.uuid.slice(0, 8)}</span>
              <span class="ac-title">{@html highlightMatch(item.titolo, parentUuid)}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  </div>

  <!-- Dependencies — MultiEntryField with autocomplete -->
  <MultiEntryField
    label="Depends On"
    hint="UUID or title of blocker"
    bind:entries={dependencyUuids}
    placeholder="Search by title or enter UUID"
    autocompleteQuery={searchDepTitle}
  />

  <!-- Tags — free-text MultiEntryField -->
  <MultiEntryField
    label="Tags"
    hint="Add labels to organize (creates new tags if needed)"
    bind:entries={tags}
    placeholder="Enter tag name"
  />

  <!-- File attachment -->
  <MultiEntryField
    label="File Attachment"
    hint="Local path or URL — one per chip"
    bind:entries={filePaths}
    placeholder="/path/to/file or https://..."
  />

  <div class="actions">
    <button type="button" class="draft-btn" onclick={saveDraft} disabled={savingDraft || !title && !description}>
      {#if savingDraft}
        Saving…
      {:else if draftSaved}
        Draft saved ✓
      {:else}
        Save Draft <kbd>Ctrl+S</kbd>
      {/if}
    </button>
    <button type="submit" disabled={adding || !title}>
      {adding ? "Adding..." : "Add Todo"} <kbd>Ctrl+Enter</kbd>
    </button>
  </div>

  {#if cowrite.isActive}
    <CowritePanel {cowrite} />
  {/if}
</form>

<svelte:window onkeydown={handleFormKeydown} />

<style>
  .todo-add-form { padding: 1rem 1rem 0 1rem; display: flex; flex-direction: column; gap: 0.75rem; position: relative; }
  .form-toolbar {
    display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0;
    margin: -1rem -1rem 0 -1rem; padding: 0.4rem 0.5rem;
    background: #16162a; border-bottom: 1px solid #333; min-height: 2.2rem;
    flex-shrink: 0; font-family: monospace; font-size: 0.82rem;
  }
  .toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 0.5rem; }
  .toolbar-right { margin-left: auto; }
  .toolbar-title { color: #b0b0c0; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; }
  .row-fields { display: flex; gap: 0.75rem; }
  .row-fields .field { flex: 1; }
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label {
    font-size: 0.78rem; color: var(--clr-sub); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em;
  }
  .field-hint {
    font-weight: 400; text-transform: none; letter-spacing: 0;
    color: var(--clr-dim); font-size: 0.7rem;
  }
  .field input, .field textarea, .field select {
    background: #16213e; border: 1px solid #333; color: #e0e0e0;
    padding: 0.5rem 0.6rem; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
    outline: none; transition: border-color 0.15s;
  }
  .field input:focus, .field textarea:focus, .field select:focus {
    border-color: #5a5a8a;
  }
  .field select { cursor: pointer; }
  .field textarea { resize: vertical; min-height: 80px; font-family: inherit; line-height: 1.5; }
  .required-badge {
    display: inline-block; font-size: 0.55rem; text-transform: uppercase;
    background: #5b2020; color: #e0a0a0; padding: 0.08rem 0.4rem;
    border-radius: 3px; font-weight: 600; vertical-align: middle; margin-left: 0.3rem;
  }
  .template-fields {
    border: 1px solid #2a2a3e; border-radius: 4px; padding: 0.75rem;
    background: #16162a;
  }
  .template-fields h4 {
    margin: 0 0 0.6rem; font-size: 0.72rem; color: var(--clr-muted);
    text-transform: uppercase; letter-spacing: 0.08em;
  }
  .autocomplete-field .autocomplete-wrapper { position: relative; }
  .autocomplete-dropdown {
    position: absolute; top: 100%; left: 0; right: 0; z-index: 100;
    background: #1e1e36; border: 1px solid #4a4a6a; border-top: none;
    border-radius: 0 0 4px 4px; max-height: 200px; overflow-y: auto;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }
  .autocomplete-item {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.35rem 0.5rem; cursor: pointer; font-size: 0.82rem;
  }
  .autocomplete-item:hover { background: #2a2a4e; }
  .ac-uuid { color: var(--clr-dim); font-size: 0.72rem; flex-shrink: 0; min-width: 4rem; font-family: monospace; }
  .ac-title { color: #e0e0e0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ac-title :global(mark) {
    background: #3a5a3a; color: #d0e8d0; padding: 0 2px; border-radius: 2px;
  }
  .actions { display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: 0.25rem; }
  .actions button {
    background: #0f3460; color: #e0e0e0; border: none; padding: 0.5rem 1.5rem;
    border-radius: 4px; cursor: pointer; font-size: 0.85rem; font-family: inherit;
    transition: background 0.15s;
  }
  .actions button:disabled { opacity: 0.4; cursor: not-allowed; }
  .actions button:hover:not(:disabled) { background: #1a4a7a; }
  .draft-btn {
    background: #2a2a3e;
    border: 1px solid #444;
    color: #ccc;
    margin-right: auto;
  }
  .draft-btn:hover:not(:disabled) { background: #3a3a5a; }
  .draft-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .draft-btn kbd {
    display: inline-block;
    padding: 1px 4px;
    background: #222;
    border: 1px solid #555;
    border-radius: 3px;
    font-size: 0.7rem;
    margin-left: 0.2rem;
  }
</style>
