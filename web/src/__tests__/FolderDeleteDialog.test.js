/**
 * FolderDeleteDialog component tests — 2-level delete confirmation.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { flushSync } from "svelte";
import FolderDeleteDialog from "../lib/FolderDeleteDialog.svelte";

// Mock the email API for folder loading
const mockListFolders = vi.fn();
vi.mock("../lib/api.js", () => ({
  email: {
    listFolders: (...args) => mockListFolders(...args),
  },
}));

function flushEffects() {
  flushSync();
}

describe("FolderDeleteDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListFolders.mockResolvedValue({
      folders: [
        { label: "user@example.com/Inbox", folder_name: "Inbox", account_email: "user@example.com" },
        { label: "user@example.com/Sent", folder_name: "Sent", account_email: "user@example.com" },
      ],
    });
  });

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

  it("combobox has aria-controls pointing to suggestions listbox", async () => {
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1"],
    });
    flushEffects();
    // Select "Move to another folder" to show the combobox
    const moveRadio = screen.getByDisplayValue("move");
    await fireEvent.click(moveRadio);
    flushEffects();
    // Wait for folder load and type to trigger suggestions
    await new Promise(r => setTimeout(r, 10));
    flushEffects();
    const destInput = screen.getByPlaceholderText("user@example.com/folder name");
    await fireEvent.input(destInput, { target: { value: "In" } });
    flushEffects();
    const combobox = document.querySelector('[role="combobox"]');
    expect(combobox).toBeTruthy();
    const controlsId = combobox?.getAttribute("aria-controls");
    expect(controlsId).toBeTruthy();
    // The ID should match the suggestions listbox
    const listbox = document.getElementById(controlsId);
    expect(listbox).toBeTruthy();
    expect(listbox?.getAttribute("role")).toBe("listbox");
  });

  it("suggestions listbox has id matching combobox aria-controls", async () => {
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1"],
    });
    flushEffects();
    // Select "Move to another folder" to show the combobox
    const moveRadio = screen.getByDisplayValue("move");
    await fireEvent.click(moveRadio);
    flushEffects();
    // Wait for folder load and type to trigger suggestions
    await new Promise(r => setTimeout(r, 10));
    flushEffects();
    const destInput = screen.getByPlaceholderText("user@example.com/folder name");
    await fireEvent.input(destInput, { target: { value: "In" } });
    flushEffects();
    const combobox = document.querySelector('[role="combobox"]');
    const controlsId = combobox?.getAttribute("aria-controls");
    const listbox = document.querySelector('[role="listbox"]');
    expect(listbox?.getAttribute("id")).toBe(controlsId);
  });

  it("combobox has aria-expanded attribute", async () => {
    render(FolderDeleteDialog, {
      folderPaths: ["a/F1"],
    });
    flushEffects();
    // Select "Move to another folder" to show the combobox
    const moveRadio = screen.getByDisplayValue("move");
    await fireEvent.click(moveRadio);
    flushEffects();
    // Wait for folder load and type to trigger suggestions
    await new Promise(r => setTimeout(r, 10));
    flushEffects();
    const destInput = screen.getByPlaceholderText("user@example.com/folder name");
    await fireEvent.input(destInput, { target: { value: "In" } });
    flushEffects();
    const combobox = document.querySelector('[role="combobox"]');
    expect(combobox?.hasAttribute("aria-expanded")).toBe(true);
  });
});
