<script>
  import { popup } from "./popupStore.svelte.js";
  import LoadingPopup from "./LoadingPopup.svelte";
  import StatusPopup from "./StatusPopup.svelte";
  import EmailPopup from "./EmailPopup.svelte";
  import EventsPopup from "./EventsPopup.svelte";
  import ErrorPopup from "./ErrorPopup.svelte";
  import HelpPopup from "./HelpPopup.svelte";

  function handleKeydown(e) {
    if (e.key === "Escape") {
      popup.close();
    }
  }
</script>

<svelte:window onkeydown={handleKeydown} />

{#if popup.current}
  <!-- svelte-ignore a11y_click_events_have_key_events -->
  <div class="popup-panel" role="region" aria-label="Command result">
    <header>
      <h2>{popup.current.title}</h2>
      <button class="close-btn" onclick={() => popup.close()} aria-label="Close">
        ✕
      </button>
    </header>
    <div class="body">
      {#if popup.current.type === "loading"}
        <LoadingPopup message={popup.current.title} />
      {:else if popup.current.type === "status"}
        <StatusPopup data={popup.current.data} />
      {:else if popup.current.type === "email"}
        <EmailPopup data={popup.current.data} />
      {:else if popup.current.type === "events"}
        <EventsPopup data={popup.current.data} />
      {:else if popup.current.type === "error"}
        <ErrorPopup data={popup.current.data} />
      {:else if popup.current.type === "help"}
        <HelpPopup data={popup.current.data} />
      {:else}
        <StatusPopup data={popup.current.data} />
      {/if}
    </div>
  </div>
{/if}

<style>
  .popup-panel {
    background: #1e1e32;
    border: 1px solid #444;
    border-top: none;
    border-radius: 0 0 8px 8px;
    max-width: 640px;
    width: 100%;
    margin: 0 auto;
    max-height: 60vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
    animation: slideDown 0.12s ease;
    overflow: hidden;
  }
  @keyframes slideDown {
    from { max-height: 0; opacity: 0; }
    to { max-height: 60vh; opacity: 1; }
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 1rem;
    border-bottom: 1px solid #333;
    flex-shrink: 0;
  }
  header h2 {
    font-size: 0.85rem;
    font-weight: 600;
    color: #7c7c9a;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .close-btn {
    background: none;
    border: none;
    color: #7c7c9a;
    font-size: 1rem;
    cursor: pointer;
    padding: 0.2rem;
    line-height: 1;
  }
  .close-btn:hover {
    color: #fff;
  }
  .body {
    padding: 0.75rem 1rem;
    overflow-y: auto;
    flex: 1;
  }
</style>
