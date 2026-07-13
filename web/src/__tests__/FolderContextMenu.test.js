/**
 * FolderContextMenu component tests — right-click context menu for folder tree.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { flushSync } from "svelte";
import FolderContextMenu from "../lib/FolderContextMenu.svelte";

function flushEffects() {
  flushSync();
}

describe("FolderContextMenu", () => {
  it("renders folder path in header", () => {
    render(FolderContextMenu, {
      x: 100,
      y: 200,
      folderPath: "user@example.com/MyFolder",
    });
    flushEffects();
    expect(screen.getByText("user@example.com/MyFolder")).toBeTruthy();
  });

  it("renders Rename and Delete buttons", () => {
    render(FolderContextMenu, {
      x: 100,
      y: 200,
      folderPath: "test/MyFolder",
    });
    flushEffects();
    expect(screen.getByText("✏️ Rename")).toBeTruthy();
    expect(screen.getByText("🗑️ Delete")).toBeTruthy();
  });

  it("calls onRename when Rename clicked", async () => {
    const onRename = vi.fn();
    render(FolderContextMenu, {
      x: 100,
      y: 200,
      folderPath: "acct/Fld",
      onRename,
    });
    flushEffects();
    await fireEvent.click(screen.getByText("✏️ Rename"));
    expect(onRename).toHaveBeenCalledWith("acct/Fld");
  });

  it("calls onDelete when Delete clicked", async () => {
    const onDelete = vi.fn();
    render(FolderContextMenu, {
      x: 100,
      y: 200,
      folderPath: "acct/Fld",
      onDelete,
    });
    flushEffects();
    await fireEvent.click(screen.getByText("🗑️ Delete"));
    expect(onDelete).toHaveBeenCalledWith("acct/Fld");
  });

  it("calls onClose when Rename clicked", async () => {
    const onClose = vi.fn();
    const onRename = vi.fn();
    render(FolderContextMenu, {
      x: 100,
      y: 200,
      folderPath: "acct/Fld",
      onRename,
      onClose,
    });
    flushEffects();
    await fireEvent.click(screen.getByText("✏️ Rename"));
    expect(onClose).toHaveBeenCalled();
  });

  it("calls onClose when Delete clicked", async () => {
    const onClose = vi.fn();
    const onDelete = vi.fn();
    render(FolderContextMenu, {
      x: 100,
      y: 200,
      folderPath: "acct/Fld",
      onDelete,
      onClose,
    });
    flushEffects();
    await fireEvent.click(screen.getByText("🗑️ Delete"));
    expect(onClose).toHaveBeenCalled();
  });
});
