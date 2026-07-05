<script>
  import ConfirmDialog from "./ConfirmDialog.svelte";

  let {
    message = "",
    confirmText = "Yes, Delete Everything",
    onConfirm = async () => {},
    onDismiss = () => {},
  } = $props();
</script>

<div class="reset-confirm">
  <ConfirmDialog
    title="⚠ Reset Lighterbird"
    {message}
    {confirmText}
    variant="danger"
    {onConfirm}
    {onDismiss}
  />
</div>

<style>
  .reset-confirm {
    position: absolute;
    inset: 0;
    z-index: 200;
  }
</style>
