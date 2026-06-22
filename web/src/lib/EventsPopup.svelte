<script>
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
          <div class="desc">{event.description}</div>
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
    color: #5a5a7a;
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
    color: #7c7c9a;
    font-size: 0.85rem;
    margin-top: 0.2rem;
  }
  .sep {
    margin: 0 0.4rem;
  }
  .desc {
    color: #999;
    font-size: 0.8rem;
    margin-top: 0.2rem;
  }
</style>
