/**
 * EmailListToolbar component tests — context-aware toolbar rendering.
 *
 * Validates that buttons appear/hide based on isTrashView, isDraftView,
 * and selectionMode props. This fixes the regression where stale state
 * from $state() instead of $derived() caused toolbar to show "Fldrs"
 * in trash view and vice versa.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/svelte";
import EmailListToolbar from "../lib/EmailListToolbar.svelte";

describe("EmailListToolbar", () => {
  const defaultProps = {
    selectionMode: false,
    numSelected: 0,
    showSearch: false,
    searchQuery: "",
    showFolderTree: false,
    isTrashView: false,
    isDraftView: false,
    syncing: false,
    syncProgress: null,
    onToggleMode: () => {},
    onDelete: () => {},
    onHardDelete: () => {},
    onClearTrash: () => {},
    onRestore: () => {},
    onMove: () => {},
    onToggleSearch: () => {},
    onSearchInput: () => {},
    onSearchClear: () => {},
    onSearchEscape: () => {},
    onSearchEnter: () => {},
    onToggleFolderTree: () => {},
    onToggleSortDropdown: () => {},
    onToggleParamsDialog: () => {},
    onImport: () => {},
    onExport: () => {},
    onSync: () => {},
    onToggleAdvancedSearch: () => {},
  };

  describe("view mode toolbar", () => {
    it('shows "Fldrs" button when NOT in trash view', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, isTrashView: false },
      });
      expect(container.textContent).toContain("Fldrs");
      expect(container.textContent).not.toContain("Clear Trash");
    });

    it('shows "Clear Trash" button when in trash view', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, isTrashView: true },
      });
      expect(container.textContent).toContain("Clear Trash");
      expect(container.textContent).not.toContain("Fldrs");
    });

    it('hides "+ New" button in trash view', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, isTrashView: true, onNew: () => {} },
      });
      expect(container.textContent).not.toContain("+ New");
    });

    it('shows "+ New" button when onNew is provided and NOT trash view', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, isTrashView: false, onNew: () => {} },
      });
      expect(container.textContent).toContain("+ New");
    });

    it('shows "Import" button in draft view', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, isDraftView: true },
      });
      expect(container.textContent).toContain("Import");
    });

    it('hides "Import" button when NOT in draft view', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, isDraftView: false },
      });
      expect(container.textContent).not.toContain("Import");
    });
  });

  describe("selection mode toolbar", () => {
    it('shows "Move" button when NOT in trash view', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, selectionMode: true, numSelected: 1, isTrashView: false },
      });
      expect(container.textContent).toContain("Move");
    });

    it('hides "Move" button in trash view, shows "Restore" instead', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, selectionMode: true, numSelected: 1, isTrashView: true },
      });
      expect(container.textContent).toContain("Restore");
      expect(container.textContent).not.toContain("Move");
    });

    it('shows "Clear Trash" button in trash view selection mode', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, selectionMode: true, isTrashView: true },
      });
      expect(container.textContent).toContain("Clear Trash");
    });

    it('shows "Delete" button when NOT in trash view', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, selectionMode: true, numSelected: 1, isTrashView: false },
      });
      expect(container.textContent).toContain("Delete");
    });

    it('hides "Delete" button in trash view', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, selectionMode: true, isTrashView: true },
      });
      expect(container.textContent).not.toContain("Delete");
    });
  });

  // Search mode toolbar behavior (Fldrs vs Clear Trash) follows the same
  // isTrashView logic as view mode, tested above.  ListSearchBar manages
  // its own focus state internally; action buttons only appear after the
  // search is "confirmed" (blur), which jsdom doesn't fully replicate.

  describe("shortcut hints in buttons", () => {
    it('shows Ctrl+E hint on Export button', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, selectionMode: true, numSelected: 1 },
      });
      // Check for Ctrl+E or ⌃E in the Export button
      const exportBtn = container.querySelector('[title*="Export"]');
      expect(exportBtn).toBeTruthy();
      expect(exportBtn.textContent).toMatch(/⌃E|Ctrl\+E/);
    });

    it('shows M hint on Move button (not Ctrl+M)', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, selectionMode: true, numSelected: 1, isTrashView: false },
      });
      const moveBtn = container.querySelector('[title*="Move"]');
      expect(moveBtn).toBeTruthy();
      expect(moveBtn.textContent).toContain("M");
      expect(moveBtn.textContent).not.toContain("⌃M");
    });

    it('shows Ctrl+M hint on Import button (draft view)', () => {
      const { container } = render(EmailListToolbar, {
        props: { ...defaultProps, isDraftView: true },
      });
      const importBtn = container.querySelector('[title*="Import"]');
      expect(importBtn).toBeTruthy();
      expect(importBtn.textContent).toMatch(/⌃M|Ctrl\+M/);
    });
  });
});
