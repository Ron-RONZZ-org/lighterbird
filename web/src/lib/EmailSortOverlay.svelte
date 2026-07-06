<script>
  /**
   * EmailSortOverlay.svelte
   *
   * Dropdown overlay wrapping SortDropdown with $bindable state so the
   * parent doesn't need intermediary callback functions.  State is shared
   * via $bindable — changes flow both ways automatically.
   *
   * Props:
   *   sort                — (bindable) current sort order
   *   groupByConversation — (bindable) group by conversation toggle
   *   groupBySender       — (bindable) group by sender toggle
   *   show                — (bindable) overlay visibility
   *   onRefresh           — callback after a sort/group change
   *   onClose             — callback when backdrop is clicked
   */
  import DropdownPanel from "./DropdownPanel.svelte";
  import SortDropdown from "./SortDropdown.svelte";

  let {
    sort = $bindable("newest"),
    groupByConversation = $bindable(false),
    groupBySender = $bindable(false),
    show = $bindable(false),
    onRefresh = async () => {},
    onClose = () => {},
  } = $props();

  function handleSortChange(val) {
    sort = val;
    groupBySender = false;
    onRefresh();
  }

  function handleGroupChange(val) {
    groupByConversation = val;
    onRefresh();
  }

  function handleGroupBySenderChange(val) {
    groupBySender = val;
    onRefresh();
  }
</script>

<DropdownPanel {show} {onClose}>
  <div class="sort-panel">
    <SortDropdown
      {sort}
      {groupByConversation}
      {groupBySender}
      onSortChange={handleSortChange}
      onGroupChange={handleGroupChange}
      onGroupBySenderChange={handleGroupBySenderChange}
    />
  </div>
</DropdownPanel>

<style>
  .sort-panel {
    padding: 0.75rem;
  }
</style>
