<script>
  /** Interactive form tab — routes to the correct form component based on data.form.
   *
   * Each form calls onsubmit() with a structured command payload:
   *   { tokens: string[], flags: object, remaining: string[] }
   * which gets sent to POST /api/v1/command.
   */

  import { tabStore } from "./tabStore.svelte.js";
  import ComposeEmail from "./ComposeEmail.svelte";
  import JournalWrite from "./JournalWrite.svelte";
  import TodoAddForm from "./TodoAddForm.svelte";
  import EventForm from "./EventForm.svelte";

  let { data = {} } = $props();
  let formType = $derived(data?.form || "");
  let initialData = $derived(data?.initialData || {});

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

      // Close form tab, open result tab
      const activeId = tabStore.active?.id;
      if (activeId) tabStore.close(activeId);
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

  /** Cancel / close the form tab. */
  function handleCancel() {
    const activeId = tabStore.active?.id;
    if (activeId) tabStore.close(activeId);
  }
</script>

<div class="form-tab">
  <div class="form-header">
    <span class="form-title">{formType.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}</span>
    <button class="cancel-btn" onclick={handleCancel} aria-label="Cancel">✕</button>
  </div>

  {#if formType === "email-send"}
    <ComposeEmail {initialData} onsubmit={handleFormSubmit} />
  {:else if formType === "journal-write"}
    <JournalWrite {initialData} onsubmit={handleFormSubmit} />
  {:else if formType === "todo-add"}
    <TodoAddForm {initialData} onsubmit={handleFormSubmit} />
  {:else if formType === "calendar-event-add"}
    <EventForm {initialData} onsubmit={handleFormSubmit} />
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
