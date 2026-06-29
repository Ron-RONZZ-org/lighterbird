<script>
  /** Interactive form tab — routes to the correct form component based on data.form.
   *
   * Each form calls onsubmit() with a structured command payload:
   *   { tokens: string[], flags: object, remaining: string[] }
   * which gets sent to POST /api/v1/command.
   *
   * Supports three categories:
   *   Level 1 — Dedicated forms (complex UI): ComposeEmail, JournalWrite, TodoAddForm, EventForm
   *   Level 2 — DynamicForm (generic from tree metadata): contacts, accounts, templates, etc.
   *   Level 3 — Sieve editor (dedicated): SieveEditorForm
   */

  import { tabStore } from "./tabStore.svelte.js";
  import { journal as journalApi, todo as todoApi, contacts as contactsApi, calendar as calendarApi } from "./api.js";
  import ComposeEmail from "./ComposeEmail.svelte";
  import JournalWrite from "./JournalWrite.svelte";
  import TodoAddForm from "./TodoAddForm.svelte";
  import EventForm from "./EventForm.svelte";
  import DynamicForm from "./DynamicForm.svelte";
  import SieveEditorForm from "./SieveEditorForm.svelte";

  /** List refreshers keyed by _returnIdKey — fetch fresh data with highlight. */
  const LIST_REFRESHERS = {
    "persistent-journal-list":         (highlight) => journalApi.list({ limit: 50 }).then(r => ({ ...r, highlight })),
    "persistent-todo-list":            (highlight) => todoApi.list({ limit: 50 }).then(r => ({ ...r, highlight })),
    "persistent-contacts-list":        (highlight) => contactsApi.list({ limit: 50 }).then(r => ({ ...r, highlight })),
    "persistent-calendar-events":      (highlight) => calendarApi.listEvents({ limit: 50 }).then(r => ({ ...r, highlight })),
  };

  let { data = {} } = $props();
  let formType = $derived(data?.form || "");
  let initialData = $derived(data?.initialData || {});
  let commandPath = $derived(data?.commandPath || _inferCommandPath(formType));
  let formDirty = $state(false);

  function handleDirtyChange(dirty) {
    formDirty = dirty;
  }

  /** Infer command path from form type name */
  function _inferCommandPath(formType) {
    const map = {
      "contacts-add": ["contacts", "add"],
      "contacts-modify": ["contacts", "modify"],
      "email-account-add": ["email", "account", "add"],
      "email-account-modify": ["email", "account", "modify"],
      "calendar-account-add": ["calendar", "account", "add"],
      "calendar-account-modify": ["calendar", "account", "modify"],
      "todo-template-add": ["todo", "template", "add"],
      "todo-template-modify": ["todo", "template", "modify"],
      "user-saved-commands-add": ["user", "saved-commands", "add"],
      "user-saved-commands-modify": ["user", "saved-commands", "modify"],
      "llm-profile-new": ["llm", "profile", "new"],
      "llm-profile-set": ["llm", "profile", "set"],
      "backup-config-add": ["backup", "config", "add"],
      "backup-config-modify": ["backup", "config", "modify"],
      "backup-prune": ["backup", "prune"],
      "sync": ["sync"],
    };
    return map[formType] || [];
  }

  let submitting = $state(false);

  /** Submit form data to the command endpoint. */
  async function handleFormSubmit(payload) {
    if (submitting) return;
    submitting = true;
    try {
      // Include remaining positional args in the tokens array
      const allTokens = [...(payload.tokens || []), ...(payload.remaining || [])];
      const resp = await fetch("/api/v1/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tokens: allTokens,
          flags: payload.flags || {},
          raw_input: "!" + allTokens.join(" "),
        }),
      });

      const result = await resp.json();

      if (!resp.ok) {
        const detail = result.detail || {};
        const msg = typeof detail === "string" ? detail : detail.error || `HTTP ${resp.status}`;
        const suggestion = detail.suggestion || "";
        tabStore.open("error", "Command Failed", { message: msg, suggestion });
        return;
      }

      // Read return-to-list values BEFORE closing (component may unmount)
      const returnIdKey = initialData?._returnIdKey;
      const highlightUuid = result.data?.uuid;
      const returnType = initialData?._returnType;
      const returnTitle = initialData?._returnTitle;

      // Close form tab
      const activeId = tabStore.active?.id;
      if (activeId) tabStore.close(activeId);

      if (returnIdKey && highlightUuid && LIST_REFRESHERS[returnIdKey]) {
        // Navigate to list tab with highlight on the new item
        try {
          const freshData = await LIST_REFRESHERS[returnIdKey](highlightUuid);
          tabStore.open(returnType || "status", returnTitle || "Done", freshData, { idKey: returnIdKey });
          return;
        } catch {
          // Refresh failed — fall through to open result tab
        }
      }

      tabStore.open(result.type || "status", result.title || "Done", result.data || {});
    } catch (err) {
      const msg = err.cause?.code === "ECONNREFUSED"
        ? "Cannot connect to the backend."
        : `Error: ${err.message}`;
      tabStore.open("error", "Submission Failed", { message: msg });
    } finally {
      submitting = false;
    }
  }

  /** Cancel / close the form tab. Warns if there are unsaved changes. */
  function handleCancel() {
    if (formDirty) {
      if (!confirm("You have unsaved changes. Discard them?")) return;
    }
    const activeId = tabStore.active?.id;
    if (activeId) tabStore.close(activeId);
  }

  /** Human-readable title for the form type. */
  let displayTitle = $derived(
    formType === "email-send" ? "Compose Email"
    : formType === "journal-write" ? "Write Journal Entry"
    : formType === "todo-add" ? "Add Todo"
    : formType === "calendar-event-add" ? "Add Calendar Event"
    : formType === "email-sieve-add" ? "New Sieve Script"
    : formType === "email-sieve-modify" ? "Edit Sieve Script"
    : formType.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
  );
</script>

<div class="form-tab">
  <div class="form-header">
    <span class="form-title">{displayTitle}</span>
    <button class="cancel-btn" onclick={handleCancel} aria-label="Cancel">✕</button>
  </div>

  {#if formType === "email-send"}
    <ComposeEmail {initialData} onsubmit={handleFormSubmit} onDirtyChange={handleDirtyChange} />
  {:else if formType === "journal-write"}
    <JournalWrite {initialData} onsubmit={handleFormSubmit} onDirtyChange={handleDirtyChange} />
  {:else if formType === "todo-add"}
    <TodoAddForm {initialData} onsubmit={handleFormSubmit} onDirtyChange={handleDirtyChange} />
  {:else if formType === "calendar-event-add"}
    <EventForm {initialData} onsubmit={handleFormSubmit} onDirtyChange={handleDirtyChange} />
  {:else if formType === "email-sieve-add" || formType === "email-sieve-modify"}
    <SieveEditorForm data={formType === "email-sieve-modify" ? { script: initialData } : {}} />
  {:else if commandPath.length > 0}
    <DynamicForm {commandPath} {initialData} onsubmit={handleFormSubmit} />
  {:else}
    <p class="unknown-form">Unknown form type: {formType}</p>
  {/if}
</div>

<style>
  .form-tab {
    display: flex;
    flex-direction: column;
    height: 100%;
    overflow-y: auto;
  }
  .form-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.5rem 1rem;
    border-bottom: 1px solid #333;
    background: #16162a;
    flex-shrink: 0;
  }
  .form-title {
    font-family: monospace;
    font-size: 0.9rem;
    color: #e0e0e0;
    font-weight: 600;
  }
  .cancel-btn {
    background: none;
    border: none;
    color: #7c7c9a;
    font-size: 1rem;
    cursor: pointer;
    padding: 0.2rem 0.4rem;
    border-radius: 4px;
  }
  .cancel-btn:hover {
    background: #2a2a44;
    color: #e0e0e0;
  }
  .unknown-form {
    color: #c44;
    text-align: center;
    padding: 2rem;
    font-family: monospace;
  }
</style>
