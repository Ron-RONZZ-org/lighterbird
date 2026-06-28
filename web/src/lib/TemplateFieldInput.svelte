<script>
  /** Renders a single template field input with proper two-way binding. */
  let { field, value = "", onchange } = $props();

  function handleInput(e) {
    onchange?.(e.target.value);
  }
</script>

{#if field.kampo_tipo === 'markdown'}
  <textarea
    id="tpl-{field.kampo_nomo}"
    value={value}
    oninput={handleInput}
    rows="5"
    placeholder="Enter {field.kampo_nomo}..."
    required={!!field.estas_deviga}
  ></textarea>
{:else if field.kampo_tipo === 'file'}
  <input
    id="tpl-{field.kampo_nomo}"
    type="text"
    value={value}
    oninput={handleInput}
    placeholder="File path or URL for {field.kampo_nomo}"
    required={!!field.estas_deviga}
  />
{:else}
  <input
    id="tpl-{field.kampo_nomo}"
    type="text"
    value={value}
    oninput={handleInput}
    placeholder="Enter {field.kampo_nomo}"
    required={!!field.estas_deviga}
  />
{/if}
