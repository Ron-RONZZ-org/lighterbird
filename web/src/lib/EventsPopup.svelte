<script>
  import { renderMarkdown } from "./markdown.js";

  let { data = {} } = $props();
  let events = $derived(data.events || []);
</script>

<div class="events">
  {#if events.length === 0}
    <p class="empty">No events in this date range.</p>
  {:else}
    {#each events as event}
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
  {/if}
</div>

<style>
  .events {
    font-family: system-ui, monospace;
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
</style>
