import { describe, it, expect } from "vitest";
import { resolveCidUrls } from "../lib/emailCidResolver.js";

const UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
const CID_BASE = `/api/v1/email/messages/${UUID}/cid/`;

describe("resolveCidUrls", () => {
  it("returns empty string for null/undefined htmlBody", () => {
    expect(resolveCidUrls(null, UUID)).toBe("");
    expect(resolveCidUrls(undefined, UUID)).toBe("");
  });

  it("returns htmlBody unchanged when messageUuid is missing", () => {
    const html = "<p>hello</p>";
    expect(resolveCidUrls(html, "")).toBe(html);
    expect(resolveCidUrls(html, null)).toBe(html);
    expect(resolveCidUrls(html, undefined)).toBe(html);
  });

  it("rewrites src=\"cid:...\" with double quotes", () => {
    const input = '<img src="cid:image001.jpg@01DD15E7.CEDBC180">';
    const expected = `<img src="${CID_BASE}image001.jpg@01DD15E7.CEDBC180">`;
    expect(resolveCidUrls(input, UUID)).toBe(expected);
  });

  it("rewrites src='cid:...' with single quotes", () => {
    const input = "<img src='cid:logo@local'>";
    const expected = `<img src='${CID_BASE}logo@local'>`;
    expect(resolveCidUrls(input, UUID)).toBe(expected);
  });

  it("rewrites src=cid:... without quotes", () => {
    const input = "<img src=cid:logo@local>";
    const expected = `<img src="${CID_BASE}logo@local">`;
    expect(resolveCidUrls(input, UUID)).toBe(expected);
  });

  it("rewrites multiple cid: references in one HTML body", () => {
    const input =
      '<img src="cid:img1@a"><br><img src="cid:img2@b">';
    const expected =
      `<img src="${CID_BASE}img1@a"><br><img src="${CID_BASE}img2@b">`;
    expect(resolveCidUrls(input, UUID)).toBe(expected);
  });

  it("does not modify regular src= URLs", () => {
    const input = '<img src="https://example.com/photo.jpg">';
    expect(resolveCidUrls(input, UUID)).toBe(input);
  });

  it("does not modify src with non-cid protocol", () => {
    const input = '<img src="data:image/png;base64,abc">';
    expect(resolveCidUrls(input, UUID)).toBe(input);
  });

  it("handles HTML with mixed cid and regular URLs", () => {
    const input =
      '<img src="cid:inline@img"><img src="https://cdn.example.com/logo.png">';
    const result = resolveCidUrls(input, UUID);
    expect(result).toContain(`${CID_BASE}inline@img`);
    expect(result).toContain("https://cdn.example.com/logo.png");
  });

  it("handles case-insensitive CID prefix", () => {
    const input = '<img src="CID:Image001.JPG@domain">';
    const expected = `<img src="${CID_BASE}Image001.JPG@domain">`;
    expect(resolveCidUrls(input, UUID)).toBe(expected);
  });
});
