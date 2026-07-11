<script>
  /**
   * ConfirmToolDialog — Re-export of the shared ConfirmDialog from lightercore.
   *
   * Previously had its own implementation; now delegates to the shared
   * @lightercore/ui/ConfirmDialog which provides the richer interaction
   * (per-item feedback, global feedback, approve-all toggle, explicit submit).
   *
   * Accepts both the old-style `onConfirm(decisions)` and the new-style
   * `onSubmit(decisions, feedback)` callback for backward compatibility.
   */
  import SharedConfirmDialog from "@lightercore/ui/ConfirmDialog.svelte";

  let {
    batch = [],
    message = "",
    onConfirm = () => {},
    onSubmit = null,
    onDismiss = () => {},
  } = $props();

  function handleSubmit(decisions, feedback) {
    if (onSubmit) {
      onSubmit(decisions, feedback);
    } else {
      onConfirm(decisions);
    }
  }
</script>

<SharedConfirmDialog
  {batch}
  {message}
  onSubmit={handleSubmit}
  {onDismiss}
/>
