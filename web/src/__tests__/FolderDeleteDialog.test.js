/**
 * FolderDeleteDialog component tests — 2-level delete confirmation.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { flushSync } from "svelte";
import FolderDeleteDialog from "../lib/FolderDeleteDialog.svelte";

function flushEffects() {
  flushSync();
}

describe("FolderDeleteDialog", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders folder path in message", () => {
    render(FolderDeleteDialog, {
      folderPaths: ["acct@x.com/MyFolder"],
    });
    flushEffects();
    expect(screen.getByText(/MyFolder/)).toBeTruthy();
  });

  it("shows count for batch delete", () => {
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1", "a/F2", "a/F3"],
    });
    flushEffects();
    expect(screen.getByText(/(3) folders/)).toBeTruthy();
  });

  it("renders disposition radio buttons", () => {
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1"],
    });
    flushEffects();
    expect(screen.getByText("Move to Trash")).toBeTruthy();
    expect(screen.getByText("Move to another folder")).toBeTruthy();
  });

  it("trash is selected by default", () => {
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1"],
    });
    flushEffects();
    const trashRadio = screen.getByDisplayValue("trash");
    expect(trashRadio.checked).toBe(true);
  });

  it("shows destination input when 'move' selected", async () => {
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1"],
    });
    flushEffects();
    // Select "Move to another folder"
    const moveRadio = screen.getByDisplayValue("move");
    await fireEvent.click(moveRadio);
    flushEffects();
    expect(screen.getByPlaceholderText("user@example.com/folder name")).toBeTruthy();
  });

  it("hides destination input when 'trash' selected", () => {
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1"],
    });
    flushEffects();
    const trashRadio = screen.getByDisplayValue("trash");
    expect(trashRadio.checked).toBe(true);
    expect(screen.queryByPlaceholderText("user@example.com/folder name")).toBeNull();
  });

  it("calls onDismiss on Cancel click", async () => {
    const onDismiss = vi.fn();
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1"],
      onDismiss,
    });
    flushEffects();
    await fireEvent.click(screen.getByText("Cancel"));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("calls onDelete with 'trash' disposition when trash is selected", async () => {
    const onDelete = vi.fn();
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1"],
      onDelete,
    });
    flushEffects();
    const btn = screen.getByText("Delete Folder");
    await fireEvent.click(btn);
    expect(onDelete).toHaveBeenCalledWith("trash", null);
  });

  it("Delete button is disabled when 'move' selected but no folder chosen", async () => {
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1"],
    });
    flushEffects();
    const moveRadio = screen.getByDisplayValue("move");
    await fireEvent.click(moveRadio);
    flushEffects();
    const btn = screen.getByText("Delete Folder");
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("has role alertdialog", () => {
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1"],
    });
    flushEffects();
    const dialog = document.querySelector('[role="alertdialog"]');
    expect(dialog).toBeTruthy();
    expect(dialog?.getAttribute("aria-modal")).toBe("true");
  });
});
