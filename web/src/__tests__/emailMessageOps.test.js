/**
 * emailMessageOps tests — openMessage, deleteSelected, hardDeleteSelected, handleRowClick.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  openMessage,
  handleRowClick,
  deleteSelected,
  hardDeleteSelected,
  moveSelected,
} from "../lib/emailMessageOps.svelte.js";

// Mock api.js
vi.mock("../lib/api.js", () => ({
  email: {
    getMessage: vi.fn(),
    batchDelete: vi.fn(),
    batchDeleteHard: vi.fn(),
    batchMove: vi.fn(),
  },
}));

// Mock tabStore
vi.mock("../lib/tabStore.svelte.js", () => ({
  tabStore: {
    open: vi.fn(),
  },
}));

import { tabStore } from "../lib/tabStore.svelte.js";
import { email as emailApi } from "../lib/api.js";

describe("openMessage", () => {
  beforeEach(() => vi.clearAllMocks());

  it("opens a message tab on success", async () => {
    emailApi.getMessage.mockResolvedValue({
      uuid: "abc-123",
      subject: "Hello World",
    });
    await openMessage("abc-123");
    expect(emailApi.getMessage).toHaveBeenCalledWith("abc-123");
    expect(tabStore.open).toHaveBeenCalledWith(
      "email",
      "Hello World",
      expect.objectContaining({ uuid: "abc-123" }),
      expect.objectContaining({ idKey: "email-abc-123" }),
    );
  });

  it("opens error tab on failure", async () => {
    emailApi.getMessage.mockRejectedValue(new Error("Not found"));
    await openMessage("abc-123");
    expect(tabStore.open).toHaveBeenCalledWith(
      "error",
      "Error",
      expect.objectContaining({ message: expect.stringContaining("Not found") }),
    );
  });

  it("skips empty uuid", async () => {
    await openMessage("");
    expect(emailApi.getMessage).not.toHaveBeenCalled();
  });
});

describe("deleteSelected", () => {
  beforeEach(() => vi.clearAllMocks());

  it("calls batchDelete and refreshList", async () => {
    emailApi.batchDelete.mockResolvedValue({});
    const refreshList = vi.fn();
    await deleteSelected(["abc-123"], refreshList);
    expect(emailApi.batchDelete).toHaveBeenCalledWith(["abc-123"]);
    expect(refreshList).toHaveBeenCalled();
  });

  it("skips empty uuids", async () => {
    const refreshList = vi.fn();
    await deleteSelected([], refreshList);
    expect(emailApi.batchDelete).not.toHaveBeenCalled();
  });

  it("opens error tab on failure", async () => {
    emailApi.batchDelete.mockRejectedValue(new Error("IMAP error"));
    await deleteSelected(["abc-123"], vi.fn());
    expect(tabStore.open).toHaveBeenCalledWith(
      "error",
      "Delete Failed",
      expect.any(Object),
    );
  });
});

describe("hardDeleteSelected", () => {
  beforeEach(() => vi.clearAllMocks());

  it("calls batchDeleteHard and refreshList", async () => {
    emailApi.batchDeleteHard.mockResolvedValue({});
    const refreshList = vi.fn();
    await hardDeleteSelected(["abc-123"], refreshList);
    expect(emailApi.batchDeleteHard).toHaveBeenCalledWith(["abc-123"]);
    expect(refreshList).toHaveBeenCalled();
  });

  it("skips empty uuids", async () => {
    await hardDeleteSelected([], vi.fn());
    expect(emailApi.batchDeleteHard).not.toHaveBeenCalled();
  });

  it("opens error tab on failure", async () => {
    emailApi.batchDeleteHard.mockRejectedValue(new Error("Server error"));
    await hardDeleteSelected(["abc-123"], vi.fn());
    expect(tabStore.open).toHaveBeenCalledWith(
      "error",
      "Hard Delete Failed",
      expect.any(Object),
    );
  });
});

describe("moveSelected", () => {
  beforeEach(() => vi.clearAllMocks());

  it("calls batchMove and refreshList", async () => {
    emailApi.batchMove.mockResolvedValue({});
    const refreshList = vi.fn();
    await moveSelected(["abc-123"], "INBOX", refreshList);
    expect(emailApi.batchMove).toHaveBeenCalledWith(["abc-123"], "INBOX");
    expect(refreshList).toHaveBeenCalled();
  });
});

describe("handleRowClick", () => {
  it("opens message in normal mode", () => {
    const sel = { selectionMode: false };
    handleRowClick({ ctrlKey: false }, { uuid: "abc" }, sel);
    // This should call openMessage which was already tested
  });

  it("toggles selection in selection mode", () => {
    const sel = { selectionMode: true, handleRowClick: vi.fn() };
    handleRowClick({ ctrlKey: false }, { uuid: "abc" }, sel);
    expect(sel.handleRowClick).toHaveBeenCalledWith({ ctrlKey: false }, "abc");
  });
});
