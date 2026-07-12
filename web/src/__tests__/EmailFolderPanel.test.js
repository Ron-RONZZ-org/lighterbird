/**
 * EmailFolderPanel component tests — action button rendering and behavior.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { flushSync } from "svelte";
import EmailFolderPanel from "../lib/EmailFolderPanel.svelte";

function flushEffects() {
  flushSync();
}

const mockFolders = [
  { folder_name: "INBOX", account_email: "test@example.com", label: "test@example.com/INBOX" },
  { folder_name: "Sent", account_email: "test@example.com", label: "test@example.com/Sent" },
  { folder_name: "Trash", account_email: "test@example.com", label: "test@example.com/Trash" },
  { folder_name: "Archive", account_email: "test@example.com", label: "test@example.com/Archive" },
];

describe("EmailFolderPanel", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders action buttons when show=true", () => {
    render(EmailFolderPanel, {
      show: true,
      folderTree: mockFolders,
    });
    flushEffects();
    expect(screen.getByText("All")).toBeTruthy();
    expect(screen.getByText("No Trash")).toBeTruthy();
    expect(screen.getByText("None")).toBeTruthy();
  });

  it("All button fires onRefresh", () => {
    const refresh = vi.fn();
    render(EmailFolderPanel, {
      show: true,
      folderTree: mockFolders,
      onRefresh: refresh,
    });
    flushEffects();
    fireEvent.click(screen.getByText("All"));
    expect(refresh).toHaveBeenCalled();
  });

  it("None button fires onRefresh", () => {
    const refresh = vi.fn();
    render(EmailFolderPanel, {
      show: true,
      folderTree: mockFolders,
      onRefresh: refresh,
    });
    flushEffects();
    fireEvent.click(screen.getByText("None"));
    expect(refresh).toHaveBeenCalled();
  });

  it("No Trash button fires onRefresh", () => {
    const refresh = vi.fn();
    render(EmailFolderPanel, {
      show: true,
      folderTree: mockFolders,
      onRefresh: refresh,
    });
    flushEffects();
    fireEvent.click(screen.getByText("No Trash"));
    expect(refresh).toHaveBeenCalled();
  });

  it("renders search input", () => {
    render(EmailFolderPanel, {
      show: true,
      folderTree: mockFolders,
    });
    flushEffects();
    expect(screen.getByPlaceholderText("Search folders…")).toBeTruthy();
  });
});
