<script>
  /**
   * FormGuard.svelte — Dirty-form guard wrapper component.
   *
   * Wraps a form and auto-registers its dirty state with the global
   * `dirtyFormStore` (for beforeunload + tab-close guards).
   *
   * Usage (child form):
   * ```js
   *   import { getContext } from "svelte";
   *   let guard = getContext("formGuard");
   *   let dirty = $derived(…);
   *   $effect(() => { guard.setDirty(dirty); });
   * ```
   *
   * The guard is provided via Svelte 5 `setContext` — no `onDirtyChange`
   * prop needed. Backward-compatible: forms using the `onDirtyChange` prop
   * continue to work via FormTab's wiring.
   *
   * Props:
   *   tabId   — unique identifier for this tab (required for store registration)
   *   children — slot content (the form component)
   */

  import { setContext } from "svelte";
  import { createFormGuard, dirtyFormStore } from "./dirtyFormStore.svelte.js";

  let { tabId = "", children } = $props();

  let guard = $state(createFormGuard(tabId));

  // Provide guard via context so child forms can self-register
  setContext("formGuard", guard);

  // Clean up store entry on destroy
  $effect(() => {
    return () => {
      guard.clear();
    };
  });
</script>

{@render children?.()}
