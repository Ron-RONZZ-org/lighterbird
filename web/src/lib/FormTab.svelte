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

  import { onDestroy, untrack } from "svelte";
  import { tabStore } from "./tabStore.svelte.js";
  import { dirtyFormStore } from "./dirtyFormStore.svelte.js";
  import { saveCallbackStore } from "./saveCallbackStore.svelte.js";
  import { banner } from "./bannerStore.svelte.js";
  import { LIST_REFRESHERS } from "./mutationToTab.js";
  import ComposeEmail from "./ComposeEmail.svelte";
  import JournalWrite from "./JournalWrite.svelte";
  import TodoAddForm from "./TodoAddForm.svelte";
  import EventForm from "./EventForm.svelte";
  import DynamicForm from "./DynamicForm.svelte";
  import SieveEditorForm from "./SieveEditorForm.svelte";
  import LetterForm from "./LetterForm.svelte";

  let { data = {}, tabId } = $props();
  let formType = $derived(data?.form || "");
  let initialData = $derived(data?.initialData || {});
  let commandPath = $derived(data?.commandPath || _inferCommandPath(formType));
  let formDirty = $state(false);
  let formError = $state(""); // non-field-level error displayed as banner
  // Sync from prop on initial load or prop change
  $effect(() => {
    if (data?.error) formError = data.error;
  });

  function handleDirtyChange(dirty) {
    formDirty = dirty;
    // Write to the global dirtyFormStore directly — this is called
    // synchronously from the child form's $effect, which correctly tracks
    // the child's dirty $derived as a dependency.  We bypass FormTab's
    // own $effect for dirty-tracking, decoupling dirty-state propagation
    // from FormTab's reactive graph entirely.
    const tabId = tabStore.active?.id;
    if (tabId) {
      dirtyFormStore.setDirty(tabId, dirty);
    }
  }

  // Track the tab ID we registered with — used by onDestroy for cleanup.
  let _registeredTabId = null;

  // Register a default save callback that clicks the form's submit button.
  // Individual forms (ComposeEmail, LetterForm) register their own save-draft
  // callback (via onMount) which overrides this, so the UnsavedChangesDialog
  // always works regardless of form type.
  //
  // Design constraints (Svelte 5 reactive system):
  //   1. formDirty MUST be read synchronously in the $effect body so Svelte 5
  //      tracks it as a dependency (queueMicrotask reads are invisible).
  //   2. Module-level $state writes (dirtyFormStore, saveCallbackStore) MUST
  //      be deferred via queueMicrotask to avoid contributing to the mount-time
  //      flush depth.
  //   3. The $effect return (cleanup) MUST NOT write to module-level $state,
  //      because cleanup runs synchronously during $effect re-runs — if formDirty
  //      changes frequently (every keystroke), the synchronous clear+re-register
  //      cycle accumulates flush iterations.
  //   4. Therefore, cleanup is handled by onDestroy (runs once on teardown),
  //      not by the $effect return.
  //   5. tabId is read via untrack(() => tabId) so it does not establish a
  //      reactive dependency — the effect re-runs only when formDirty changes.
  $effect(() => {
    const id = untrack(() => tabId);
    // Read formDirty synchronously to establish it as a reactive dependency.
    // Svelte 5's $effect only tracks signals accessed during the synchronous
    // execution of the effect function.  Reading inside queueMicrotask below
    // (asynchronously) would NOT track it, so the effect would never re-run
    // when the user makes a form dirty — the entire unsaved-changes guard
    // would silently break for every form type.
    const dirty = formDirty;
    if (id) {
      // Register save callback once on mount (skip on re-runs from formDirty
      // changes — the callback identity hasn't changed).
      if (!_registeredTabId) {
        _registeredTabId = id;
        queueMicrotask(() => {
          saveCallbackStore.setCallback(id, () => {
            // Click the primary submit/save button in the form
            const formEl = document.querySelector('.form-tab form');
            if (formEl) {
              const btn = formEl.querySelector('button[type="submit"]');
              if (btn) { btn.click(); return; }
              // Fallback: look for common save/submit button classes
              const fallback = formEl.querySelector('.btn-primary, .btn-save, [class*="submit"]');
              if (fallback) fallback.click();
            }
          });
        });
      }
      // Sync dirty state (deferred — runs every time formDirty changes)
      queueMicrotask(() => {
        dirtyFormStore.setDirty(id, dirty);
      });
    }
    // NO return cleanup — module-level $state writes in the cleanup would
    // cascade through Svelte 5's reactive flush when formDirty changes
    // rapidly (keystrokes).  See constraint #3 above.
  });

  // Cleanup runs ONCE on component destroy, never during $effect re-runs.
  // This avoids synchronous module-level $state writes inside the flush cycle
  // that would cascade past Svelte 5's 1000-iteration guard.
  onDestroy(() => {
    if (_registeredTabId) {
      saveCallbackStore.setCallback(_registeredTabId, null);
      dirtyFormStore.clear(_registeredTabId);
    }
  });

  /** Infer command path from form type name */
  function _inferCommandPath(formType) {
    const map = {
      "contacts-add": ["contact", "add"],
      "contacts-modify": ["contact", "modify"],
      "email-account-add": ["email", "account", "add"],
      "email-account-modify": ["email", "account", "modify"],
      "calendar-account-add": ["calendar", "account", "add"],
      "calendar-account-modify": ["calendar", "account", "modify"],
      "todo-add": ["todo", "add"],
      "todo-template-add": ["todo", "template", "add"],
      "todo-template-modify": ["todo", "template", "modify"],
      "journal-write": ["journal", "write"],
      "email-sieve-add": ["email", "sieve", "add"],
      "calendar-event-add": ["calendar", "event", "add"],
      "user-saved-commands-add": ["user", "saved-commands", "add"],
      "user-saved-commands-modify": ["user", "saved-commands", "modify"],
      "user-info-add": ["user", "info", "add"],
      "user-info-modify": ["user", "info", "modify"],
      "llm-profile-new": ["llm", "profile", "new"],
      "llm-profile-set": ["llm", "profile", "set"],
      "backup-config-add": ["backup", "config", "add"],
      "backup-config-modify": ["backup", "config", "modify"],
      "backup-prune": ["backup", "prune"],
      "email-folder-add": ["email", "folder", "add"],
      "email-signature-add": ["email", "signature", "add"],
      "email-signature-modify": ["email", "signature", "modify"],
      "letter-add": ["letter", "add"],
      "letter-send": ["letter", "send"],
    };
    return map[formType] || [];
  }

  let submitting = $state(false);

  /** Submit form data to the command or REST endpoint. */
  async function handleFormSubmit(payload) {
    if (submitting) return;
    submitting = true;
    formError = "";
    try {
      let result;

      if (payload.directResult) {
        // REST direct submission (e.g. ComposeEmail via POST /api/v1/email/send)
        // Skip CLI dispatch — the form component already called the REST endpoint.
        formError = "";
        handleDirtyChange(false);
        // Wrap the REST response in a synthetic structure matching the CLI
        // response format so the post-submission navigation logic below works.
        const directFormType = payload.directFormType || formType;
        result = {
          type: "status",
          title: directFormType === "email-send" ? "Queued for Delivery" : "Done",
          data: payload.directResult,
        };
      } else {
        // CLI dispatch — send command tokens to POST /api/v1/command
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

        result = await resp.json();

        if (!resp.ok) {
          const detail = result.detail || {};
          const msg = typeof detail === "string" ? detail : detail.error || `HTTP ${resp.status}`;
          const suggestion = detail.suggestion || "";
          // Keep form open, show error banner — preserve user input
          formError = suggestion ? `${msg} — ${suggestion}` : msg;
          banner.show(formError, "error", 5000);
          return;
        }

        // Clear any previous error and dirty state
        formError = "";
        handleDirtyChange(false);
      }

      // ── Shared post-submission navigation ────────────────────────────

      // Read return-to-list values BEFORE closing (component may unmount)
      const returnIdKey = initialData?._returnIdKey;
      const highlightUuid = result.data?.uuid;
      const returnType = initialData?._returnType;
      const returnTitle = initialData?._returnTitle;

      // Close form tab using tabId prop (same as tabStore.active.id at submit time)
      if (tabId) tabStore.close(tabId);

      // ── After letter send, open render page for print/PDF download ──
      // (must happen before early returns below and before result tab open)
      const renderUrl = result.data?.render_url;

      if (returnIdKey && highlightUuid && LIST_REFRESHERS[returnIdKey]) {
        // Navigate to list tab with highlight on the new item
        try {
          const freshData = await LIST_REFRESHERS[returnIdKey](highlightUuid);
          tabStore.open(returnType || "status", returnTitle || "Done", freshData, { idKey: returnIdKey });
          if (renderUrl) window.open(renderUrl, "_blank");
          // Show confirmation banner for email sends
          if (formType === "email-send") banner.show("Queued for sending…", "success");
          return;
        } catch {
          // Refresh failed — fall through to open result tab
        }
      }

      tabStore.open(result.type || "status", result.title || "Done", result.data || {});
      if (renderUrl) window.open(renderUrl, "_blank");
      // Show confirmation banner for email sends (fallback path)
      if (formType === "email-send") banner.show("Queued for sending…", "success");
    } catch (err) {
      const msg = err.cause?.code === "ECONNREFUSED"
        ? "Cannot connect to the backend."
        : `Error: ${err.message}`;
      // Keep form open, show error banner
      formError = msg;
      banner.show(formError, "error", 5000);
    } finally {
      submitting = false;
    }
  }

  /** Cancel / close the form tab. Warns if there are unsaved changes
   *  via TabView's pendingCloseTab/UnsavedChangesDialog flow. */
  function handleCancel() {
    if (!tabId) return;
    // Always dispatch so TabView's unified handleCloseTab manages the close.
    // When formDirty is false, it closes immediately; when true, it shows
    // the UnsavedChangesDialog.  This avoids duplicating the close logic
    // which can break if tabStore state shifts between active?.id and close().
    window.dispatchEvent(new CustomEvent("request-close-tab", { detail: { tabId } }));
  }

  /** Human-readable title for the form type. */
  let displayTitle = $derived(
    formType === "email-send" ? "Compose Email"
    : formType === "journal-write" ? "Write Journal Entry"
    : formType === "todo-add" ? "Add Todo"
    : formType === "calendar-event-add" ? "Add Calendar Event"
    : formType === "email-sieve-add" ? "New Sieve Script"
    : formType === "email-sieve-modify" ? "Edit Sieve Script"
    : formType === "letter-add" ? "Add Received Letter"
    : formType === "letter-send" ? "Send Letter"
    : formType.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
  );
</script>

<div class="form-tab">
  <div class="form-header">
    <span class="form-title">{displayTitle}</span>
    <button class="cancel-btn" onclick={handleCancel} aria-label="Cancel">✕</button>
  </div>

  {#if formError}
    <div class="form-error-banner" role="alert">
      <span class="form-error-icon">✗</span>
      <span class="form-error-text">{formError}</span>
      <button class="form-error-dismiss" onclick={() => { formError = ''; }} aria-label="Dismiss">✕</button>
    </div>
  {/if}

  {#if formType === "email-send"}
    <ComposeEmail {initialData} {tabId} onsubmit={handleFormSubmit} onDirtyChange={handleDirtyChange} />
  {:else if formType === "journal-write"}
    <JournalWrite {initialData} onsubmit={handleFormSubmit} onDirtyChange={handleDirtyChange} />
  {:else if formType === "todo-add"}
    <TodoAddForm {initialData} onsubmit={handleFormSubmit} onDirtyChange={handleDirtyChange} />
  {:else if formType === "calendar-event-add"}
    <EventForm {initialData} onsubmit={handleFormSubmit} onDirtyChange={handleDirtyChange} />
  {:else if formType === "email-sieve-add" || formType === "email-sieve-modify"}
    <SieveEditorForm data={formType === "email-sieve-modify" ? { script: initialData } : {}} />
  {:else if formType === "letter-add" || formType === "letter-send"}
    <LetterForm {initialData} {tabId} formType={formType === "letter-send" ? "send" : "add"} onsubmit={handleFormSubmit} onDirtyChange={handleDirtyChange} />
  {:else if commandPath.length > 0}
    <DynamicForm {commandPath} {initialData} {tabId} onsubmit={handleFormSubmit} onDirtyChange={handleDirtyChange} />
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
  .form-error-banner {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 1rem;
    background: #3a1e1e;
    border-bottom: 1px solid #7a3a3a;
    color: #db8f8f;
    font-family: monospace;
    font-size: 0.82rem;
    flex-shrink: 0;
  }
  .form-error-icon { font-size: 0.9rem; flex-shrink: 0; }
  .form-error-text { flex: 1; min-width: 0; }
  .form-error-dismiss {
    background: none; border: none; color: #db8f8f;
    opacity: 0.6; cursor: pointer; font-size: 0.85rem;
    padding: 0.1rem 0.3rem; flex-shrink: 0;
  }
  .form-error-dismiss:hover { opacity: 1; }
  .unknown-form {
    color: #c44;
    text-align: center;
    padding: 2rem;
    font-family: monospace;
  }
</style>
