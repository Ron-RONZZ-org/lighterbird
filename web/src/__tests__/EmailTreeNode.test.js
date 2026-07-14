/**
 * EmailTreeNode component tests — folder tree node with a11y attributes.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { flushSync } from "svelte";
import EmailTreeNode from "../lib/EmailTreeNode.svelte";

function flushEffects() {
  flushSync();
}

describe("EmailTreeNode", () => {
  const baseProps = {
    node: {
      name: "INBOX",
      path: "user@example.com/INBOX",
      isFolder: true,
      expanded: false,
      children: [],
      visible: true,
    },
    depth: 0,
    showCheckboxes: true,
    activePath: "",
  };

  it("renders node name", () => {
    render(EmailTreeNode, baseProps);
    flushEffects();
    expect(screen.getByText("INBOX")).toBeTruthy();
  });

  it("treeitem span has aria-selected attribute", () => {
    render(EmailTreeNode, baseProps);
    flushEffects();
    const treeitem = document.querySelector('[role="treeitem"]');
    expect(treeitem).toBeTruthy();
    expect(treeitem?.hasAttribute("aria-selected")).toBe(true);
  });

  it("aria-selected is false when not active", () => {
    render(EmailTreeNode, { ...baseProps, activePath: "other/path" });
    flushEffects();
    const treeitem = document.querySelector('[role="treeitem"]');
    expect(treeitem?.getAttribute("aria-selected")).toBe("false");
  });

  it("aria-selected is true when active", () => {
    render(EmailTreeNode, { ...baseProps, activePath: "user@example.com/INBOX" });
    flushEffects();
    const treeitem = document.querySelector('[role="treeitem"]');
    expect(treeitem?.getAttribute("aria-selected")).toBe("true");
  });

  it("outer container has role presentation", () => {
    render(EmailTreeNode, baseProps);
    flushEffects();
    const treeNode = document.querySelector('.tree-node');
    expect(treeNode).toBeTruthy();
    expect(treeNode?.getAttribute("role")).toBe("presentation");
  });

  it("renders expand button for folders with children", () => {
    render(EmailTreeNode, {
      ...baseProps,
      node: {
        ...baseProps.node,
        children: [{ name: "Subfolder", path: "user@example.com/INBOX/Sub", isFolder: true, visible: true }],
      },
    });
    flushEffects();
    const expandBtn = document.querySelector(".expand-btn");
    expect(expandBtn).toBeTruthy();
  });

  it("renders checkbox when showCheckboxes is true", () => {
    render(EmailTreeNode, { ...baseProps, showCheckboxes: true });
    flushEffects();
    const checkbox = document.querySelector('.folder-check');
    expect(checkbox).toBeTruthy();
  });

  it("does not render checkbox when showCheckboxes is false", () => {
    render(EmailTreeNode, { ...baseProps, showCheckboxes: false });
    flushEffects();
    const checkbox = document.querySelector('.folder-check');
    expect(checkbox).toBeNull();
  });

  it("calls onActivate when folder is clicked", async () => {
    const onActivate = vi.fn();
    render(EmailTreeNode, { ...baseProps, onActivate });
    flushEffects();
    const label = screen.getByText("INBOX");
    await fireEvent.click(label);
    expect(onActivate).toHaveBeenCalledWith("user@example.com/INBOX");
  });
});
