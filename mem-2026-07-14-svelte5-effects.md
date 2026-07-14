# Svelte 5 $effect Best Practices (2026-07-14)

## Root Cause: effect_update_depth_exceeded in FormTab

When two separate `$effect`s in `FormTab.svelte` each wrote to module-level
`$state` stores (`saveCallbackStore._callbacks` and `dirtyFormStore._dirtyForms`),
Svelte 5's batch flush counter exceeded 1000 iterations during mount, throwing
`effect_update_depth_exceeded` and corrupting the reactive system.

**Fix**: Consolidate all store-writing `$effect`s into a single effect. Defer
non-critical writes via `queueMicrotask` to avoid contributing to mount-time
flush depth.

## Rule: Consolidate module-level $state writes

When a component writes to module-level `$state` variables (stores in `.svelte.js`
files), use a SINGLE `$effect` for ALL such writes. Each write increments Svelte 5's
internal batch flush counter. During mount, the combined depth of multiple effects
can exceed the 1000-iteration guard, silently breaking all event handlers.

```javascript
// BAD — two separate effects, each contributes to flush depth
$effect(() => { storeA.set(tabId, value); });
$effect(() => { storeB.set(tabId, value); });

// GOOD — single effect, deferred async write
$effect(() => {
  storeA.set(tabId, value);
  queueMicrotask(() => storeB.set(tabId, value));
  return () => { storeA.clear(tabId); storeB.clear(tabId); };
});
```

## Rule: Always key {#each} blocks

In Svelte 5, `{#each list as item, i}` without a key uses index-based DOM
reconciliation. When items are dynamically added/removed, closures in event
handlers can capture stale values.

```svelte
<!-- BAD -- stale closures possible -->
{#each tabStore.tabs as tab, i}
  <button onclick={() => closeTab(tab.id)}>✕</button>
{/each}

<!-- GOOD -- unique key prevents stale closures -->
{#each tabStore.tabs as tab (tab.id)}
  <button onclick={() => closeTab(tab.id)}>✕</button>
{/each}
```

## Debugging Svelte 5 Reactive Loops

When event handlers silently stop working:

1. **Check for `pageerror` events first** — use
   `page.on("pageerror", err => ...)` in Playwright. The
   `effect_update_depth_exceeded` error is thrown silently (no console.log)
   and only visible via `pageerror` or the dev server output.

2. **Consolidate effects** — if two or more `$effect`s write to module-level
   `$state` during mount, merge them into one and defer non-critical writes.

3. **Check `{#each}` keys** — missing unique keys can cause stale closures
   that make event handlers appear "dead".

## Testing with @testing-library/svelte + Svelte 5

`@testing-library/svelte` v5.4.2 cannot render Svelte 5 components with mock
child `.svelte` stubs. Attempting to mock with `{default: class {...}}` fails
with "Class constructors cannot be invoked without 'new'".

**Workaround**: Mock at the module-import level (`.js` stores, API clients)
rather than mocking child components. Test child components independently
in their own test files. Use Playwright E2E for integration testing.
