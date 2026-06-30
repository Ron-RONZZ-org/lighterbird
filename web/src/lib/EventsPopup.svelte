<script>
  import { renderMarkdown } from "./markdown.js";
  import { calendar as calendarApi } from "./api.js";
  import { tabStore } from "./tabStore.svelte.js";

  let { data = {} } = $props();

  // Support both {events: [...]} and a single event dict directly
  let eventList = $derived(data.events || (data.uuid ? [data] : []));
  let singleEvent = $derived(eventList.length === 1 ? eventList[0] : null);

  // Inline editing for single event
  let editing = $state(false);
  let editTitle = $state("");
  let editStart = $state("");
  let editEnd = $state("");
  let editLocation = $state("");
  let editDescription = $state("");
  let saving = $state(false);

  function startEdit() {
    if (!singleEvent) return;
    editing = true;
    editTitle = singleEvent.title || "";
    editStart = singleEvent.start || "";
    editEnd = singleEvent.end || "";
    editLocation = singleEvent.location || "";
    editDescription = singleEvent.description || "";
  }

  function cancelEdit() {
    editing = false;
  }

  async function saveEdit() {
    if (!singleEvent) return;
    saving = true;
    try {
      const updates = {};
      if (editTitle !== singleEvent.title) updates.title = editTitle;
      if (editStart !== singleEvent.start) updates.start = editStart;
      if (editEnd !== singleEvent.end) updates.end = editEnd;
      if (editLocation !== singleEvent.location) updates.location = editLocation;
      if (editDescription !== singleEvent.description) updates.description = editDescription;
      if (Object.keys(updates).length > 0) {
        await calendarApi.updateEvent(singleEvent.uuid, updates);
        const refreshed = await calendarApi.getEvent(singleEvent.uuid);
        // Update the tab data
        tabStore.update(tabStore.active.id, { events: [refreshed] });
      }
      editing = false;
    } catch (err) {
      // handled by caller
    } finally {
      saving = false;
    }
  }

  function handleKeydown(e) {
    if (e.key === "i" && !e.ctrlKey && !e.metaKey && !e.altKey && !editing && singleEvent) {
      const tag = e.target.tagName;
      if (tag !== "INPUT" && tag !== "TEXTAREA" && !e.target.isContentEditable) {
        e.preventDefault();
        startEdit();
      }
    }
    if (e.key === "Escape" && editing) {
      e.preventDefault();
      cancelEdit();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="events-wrapper">
  {#if singleEvent && editing}
    <!-- Single event edit mode -->
    <div class="toolbar">
      <div class="left">
        <button class="tool-btn" onclick={cancelEdit}>Cancel</button>
      </div>
      <div class="center">
        <span class="hint">Editing event</span>
      </div>
      <div class="right">
        <button class="tool-btn primary" onclick={saveEdit} disabled={saving || !editTitle}>
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
    <div class="edit-form">
      <div class="field">
        <label for="ev-title">Title</label>
        <input id="ev-title" type="text" bind:value={editTitle} required />
      </div>
      <div class="field">
        <label for="ev-start">Start</label>
        <input id="ev-start" type="text" bind:value={editStart} placeholder="ISO 8601" />
      </div>
      <div class="field">
        <label for="ev-end">End</label>
        <input id="ev-end" type="text" bind:value={editEnd} placeholder="ISO 8601" />
      </div>
      <div class="field">
        <label for="ev-location">Location</label>
        <input id="ev-location" type="text" bind:value={editLocation} />
      </div>
      <div class="field">
        <label for="ev-desc">Description</label>
        <textarea id="ev-desc" bind:value={editDescription} rows="4"></textarea>
      </div>
    </div>
  {:else if singleEvent && !editing}
    <!-- Single event view mode -->
    <div class="toolbar">
      <div class="left">
        <button class="tool-btn" onclick={startEdit} title="Edit (i)">✎ Edit <kbd>i</kbd></button>
      </div>
      <div class="center">
        <span class="hint">{singleEvent.category || ""}</span>
      </div>
      <div class="right"></div>
    </div>
    <div class="events">
      <div class="event">
        <div class="title">{singleEvent.title || "(untitled)"}</div>
        <div class="meta">
          <span class="date">{(singleEvent.start || "").slice(0, 16)}</span>
          {#if singleEvent.end}
            <span class="sep">→</span>
            <span class="date">{(singleEvent.end || "").slice(0, 16)}</span>
          {/if}
          {#if singleEvent.location}
            <span class="sep">·</span>
            <span class="loc">{singleEvent.location}</span>
          {/if}
        </div>
        {#if singleEvent.description}
          <div class="desc">{@html renderMarkdown(singleEvent.description)}</div>
        {/if}
      </div>
    </div>
  {:else if eventList.length > 0}
    <!-- Multi-event list view -->
    <div class="events">
      {#each eventList as event}
        <div class="event">
          <div class="title">{event.title || "(untitled)"}</div>
          <div class="meta">
            <span class="date">{(event.start || "").slice(0, 16)}</span>
            {#if event.location}
              <span class="sep">·</span>
              <span class="loc">{event.location}</span>
            {/if}
          </div>
          {#if event.description}
            <div class="desc">{@html renderMarkdown(event.description)}</div>
          {/if}
        </div>
      {/each}
    </div>
  {:else}
    <p class="empty">No events in this date range.</p>
  {/if}
</div>

<style>
  .events-wrapper {
    display: flex;
    flex-direction: column;
    height: 100%;
    position: relative;
  }
  .toolbar {
    display: flex; align-items: center; gap: 0.5rem;
    padding: 0.3rem 0.5rem; background: #16162a;
    border-bottom: 1px solid #333; min-height: 2.2rem;
    flex-shrink: 0; font-family: monospace; font-size: 0.82rem;
  }
  .left, .right { display: flex; align-items: center; gap: 0.5rem; }
  .center { flex: 1; text-align: center; }
  .tool-btn {
    padding: 0.25rem 0.6rem; border: 1px solid #444; border-radius: 4px;
    background: #2a2a3e; color: #e0e0e0; cursor: pointer;
    font-family: monospace; font-size: 0.8rem; transition: background 0.1s;
  }
  .tool-btn kbd {
    display: inline-block; padding: 0 3px; margin-left: 2px;
    font-family: monospace; font-size: 0.68rem; background: #222;
    border: 1px solid #555; border-radius: 3px; color: #999; line-height: 1.3;
  }
  .tool-btn:hover:not(:disabled) { background: #3a3a5e; }
  .tool-btn.primary { border-color: #3a6a3a; color: #7fdb7f; }
  .tool-btn.primary:hover { background: #1e3a1e; }
  .hint { color: #5a5a7a; font-size: 0.72rem; }
  .events {
    font-family: system-ui, monospace;
    flex: 1;
    overflow-y: auto;
    padding: 0.5rem 1rem;
  }
  .empty {
    color: var(--clr-muted);
    text-align: center;
    padding: 2rem;
  }
  .event {
    padding: 0.5rem 0;
    border-bottom: 1px solid #2a2a3e;
  }
  .event:last-child {
    border-bottom: none;
  }
  .title {
    color: #e0e0e0;
    font-weight: 600;
    font-size: 0.95rem;
  }
  .meta {
    color: var(--clr-sub);
    font-size: 0.85rem;
    margin-top: 0.2rem;
  }
  .sep {
    margin: 0 0.4rem;
  }
  .desc {
    color: #d0d0e0;
    font-size: 0.85rem;
    margin-top: 0.3rem;
    line-height: 1.5;
  }
  .desc :global(p) { margin: 0 0 0.4rem; }
  .desc :global(p:last-child) { margin-bottom: 0; }
  .desc :global(code) {
    background: #111; padding: 1px 4px; border-radius: 3px; font-size: 0.78rem;
  }
  .desc :global(pre) {
    background: #111; padding: 0.5rem; border-radius: 4px;
    overflow-x: auto; font-size: 0.8rem; margin: 0.4rem 0;
  }
  .desc :global(a) { color: #8a8acc; text-decoration: underline; }
  /* Edit form */
  .edit-form {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding: 1rem;
  }
  .field { display: flex; flex-direction: column; gap: 0.25rem; }
  .field label {
    font-size: 0.78rem; color: var(--clr-sub); font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em;
  }
  .field input, .field textarea {
    background: #16213e; border: 1px solid #333; color: #e0e0e0;
    padding: 0.5rem 0.6rem; border-radius: 4px; font-family: inherit; font-size: 0.9rem;
    outline: none; transition: border-color 0.15s;
  }
  .field input:focus, .field textarea:focus { border-color: #5a5a8a; }
  .field textarea { resize: vertical; min-height: 80px; font-family: inherit; line-height: 1.5; }
</style>