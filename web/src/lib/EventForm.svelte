<script>
  /** Event creation form — used when !calendar event add is typed interactively. */

  import { calendar as calendarApi } from "./api.js";

  let { initialData = {}, onsubmit } = $props();

  let calendarUuid = $state(initialData.calendar_uuid || "");
  let title = $state(initialData.title || "");
  let start = $state(initialData.start || "");
  let end = $state(initialData.end || "");
  let location = $state(initialData.location || "");
  let creating = $state(false);
  let calendars = $state([]);

  $effect(() => {
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
        remaining: [title, toIso(start), toIso(end), location].filter(Boolean),
      });
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
  <div class="actions">
    <button type="submit" disabled={creating || !calendarUuid || !title || !start || !end}>
      {creating ? "Creating..." : "Create Event"}
    </button>
  </div>
</form>

<style>
  .event-form { padding: 1rem; display: flex; flex-direction: column; gap: 0.75rem; }
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label { font-size: 0.8rem; color: #7c7c9a; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
  .field input, .field select {
    background: #16213e; border: 1px solid #333; color: #e0e0e0;
    padding: 0.5rem; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
  }
  .actions { display: flex; justify-content: flex-end; gap: 0.5rem; }
  .actions button {
    background: #0f3460; color: #e0e0e0; border: none; padding: 0.5rem 1.5rem;
    border-radius: 4px; cursor: pointer; font-size: 0.9rem;
  }
  .actions button:disabled { opacity: 0.5; cursor: not-allowed; }
  .actions button:hover:not(:disabled) { background: #1a4a7a; }
</style>
