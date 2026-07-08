/**
 * FormField component tests — field label, hint, required badge, error display.
 *
 * @vitest-environment jsdom
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/svelte";
import FormField from "../lib/FormField.svelte";

describe("FormField", () => {
  it("renders label text", () => {
    render(FormField, { label: "Email", children: () => "" });
    expect(screen.getByText("Email")).toBeTruthy();
  });

  it("renders required badge when required=true", () => {
    render(FormField, { label: "Name", required: true, children: () => "" });
    expect(screen.getByText("required")).toBeTruthy();
  });

  it("does not render required badge when required=false", () => {
    render(FormField, { label: "Name", required: false, children: () => "" });
    expect(screen.queryByText("required")).toBeNull();
  });

  it("renders hint text", () => {
    render(FormField, {
      label: "Email",
      hint: "user@example.com",
      children: () => "",
    });
    expect(screen.getByText("user@example.com")).toBeTruthy();
  });

  it("renders error message", () => {
    render(FormField, {
      label: "Email",
      error: "This field is required",
      children: () => "",
    });
    expect(screen.getByText("This field is required")).toBeTruthy();
  });

  it("applies has-error class when error exists", () => {
    const { container } = render(FormField, {
      label: "Email",
      error: "Invalid",
      children: () => "",
    });
    const field = container.querySelector(".field");
    expect(field?.classList.contains("has-error")).toBe(true);
  });

  it("does not apply has-error class when no error", () => {
    const { container } = render(FormField, {
      label: "Email",
      children: () => "",
    });
    const field = container.querySelector(".field");
    expect(field?.classList.contains("has-error")).toBe(false);
  });

  it("renders children as snippet", () => {
    // Svelte 5 passes children as a snippet function.
    // We verify that the form field container exists when children are provided.
    const { container } = render(FormField, {
      label: "Name",
      children: () => "<input />",
    });
    const field = container.querySelector(".field");
    expect(field).toBeTruthy();
  });

  it("applies width class when width prop is set", () => {
    const { container } = render(FormField, {
      label: "Name",
      width: "short",
      children: () => "",
    });
    const field = container.querySelector(".field");
    expect(field?.classList.contains("width-short")).toBe(true);
  });

  it("does not apply width class when width is empty", () => {
    const { container } = render(FormField, {
      label: "Name",
      children: () => "",
    });
    const field = container.querySelector(".field");
    expect(field?.classList.contains("width-short")).toBe(false);
  });

  it("skips label rendering when label is empty", () => {
    const { container } = render(FormField, { children: () => "" });
    const label = container.querySelector("label");
    expect(label).toBeNull();
  });
});
