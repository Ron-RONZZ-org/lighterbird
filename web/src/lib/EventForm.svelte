<script>
  /** Event creation form — used when !calendar event add is typed interactively. */

  import { onMount } from "svelte";
  import { calendar as calendarApi, drafts as draftsApi } from "./api.js";

  let { initialData = {}, onsubmit, onDirtyChange = () => {} } = $props();
  // svelte-ignore state_referenced_locally
  const _initial = initialData;

  let calendarUuid = $state(_initial.calendar_uuid || "");
  let title = $state(_initial.title || "");
  let start = $state(_initial.start || "");
  let end = $state(_initial.end || "");
  let location = $state(_initial.location || "");
  let description = $state(_initial.description || "");
  let creating = $state(false);
  let savingDraft = $state(false);
  let draftSaved = $state(false);
  let draftUuid = $state(_initial._draft_uuid || null);
  let calendars = $state([]);

  /** Save draft on Ctrl+S */
  async function saveDraft() {
    if (savingDraft) return;
    savingDraft = true;
    draftSaved = false;
    try {
      const result = await draftsApi.save(
        "calendar-event",
        title || "(untitled)",
        { calendar_uuid: calendarUuid, title, start, end, location, description },
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

  // Dirty state — compare current against initial
  let dirty = $derived(
    calendarUuid !== (_initial.calendar_uuid || "")
    || title !== (_initial.title || "")
    || start !== (_initial.start || "")
    || end !== (_initial.end || "")
    || location !== (_initial.location || "")
    || description !== (_initial.description || "")
  );
  $effect(() => { onDirtyChange(dirty); });

  onMount(() => {
    calendarApi.listCalendars().then((data) => {
      calendars = data.calendars || [];
      if (calendars.length > 0 && !calendarUuid) {
        calendarUuid = calendars[0].uuid;
      }
    }).catch(() => {});
  });

  /** Format datetime-local value to ISO 8601 */
  function toIso(dt) {
    if (!dt) return "";
    try { return new Date(dt).toISOString(); } catch { return dt; }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (!calendarUuid || !title || !start || !end) return;
    creating = true;
    try {
      await onsubmit({
        tokens: ["calendar", "event", "add"],
        flags: { calendar: calendarUuid },
        remaining: [title, toIso(start), toIso(end), location, description].filter(Boolean),
      });
      onDirtyChange(false);
    } finally {
      creating = false;
    }
  }
</script>

<form onsubmit={handleSubmit} class="event-form">
  <div class="field">
    <label for="calendar">Calendar</label>
    <select id="calendar" bind:value={calendarUuid}>
      {#each calendars as cal}
        <option value={cal.uuid}>{cal.url}</option>
      {/each}
    </select>
  </div>
  <div class="field">
    <label for="title">Title</label>
    <input id="title" type="text" bind:value={title} required placeholder="Event title" />
  </div>
  <div class="field">
    <label for="start">Start</label>
    <input id="start" type="datetime-local" bind:value={start} required />
  </div>
  <div class="field">
    <label for="end">End</label>
    <input id="end" type="datetime-local" bind:value={end} required />
  </div>
  <div class="field">
    <label for="location">Location</label>
    <input id="location" type="text" bind:value={location} placeholder="(optional)" />
  </div>
  <div class="field">
    <label for="description">Description</label>
    <textarea id="description" bind:value={description} placeholder="(optional)" rows="4"></textarea>
  </div>
  <div class="actions">
    <button type="button" class="draft-btn" onclick={saveDraft} disabled={savingDraft || !title && !start && !end}>
      {#if savingDraft}
        Saving…
      {:else if draftSaved}
        Draft saved ✓
      {:else}
        Save Draft <kbd>Ctrl+S</kbd>
      {/if}
    </button>
    <button type="submit" disabled={creating || !calendarUuid || !title || !start || !end}>
      {creating ? "Creating..." : "Create Event"} <kbd>Ctrl+Enter</kbd>
    </button>
  </div>
</form>

<svelte:window onkeydown={handleFormKeydown} />

<style>
  .event-form { padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label { font-size: 0.8rem; color: #7c7c9a; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .field input, .field select, .field textarea {
    background: #16213e; border: 1px solid #333; color: #e0e0e0;
    padding: 0.5rem; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
  }
  .field textarea { resize: vertical; min-height: 4rem; }
  .actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
  .actions button {
    background: #0f3460; color: #e0e0e0; border: none; padding: 0.5rem 1.5rem;
    border-radius: 4px; cursor: pointer; font-size: 0.9rem;
  }
  .actions button:disabled { opacity: 0.5; cursor: not-allowed; }
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
