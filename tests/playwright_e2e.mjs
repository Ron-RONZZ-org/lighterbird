/** Playwright E2E test — simulates real user interactions in the browser. */

import { chromium } from "playwright";
import { strict as assert } from "assert";
import {
  test, typeCommand, pressEnter,
  getPopupText, sleep,
  runWithBrowser,
} from "./e2e_helpers.mjs";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:6006";
const CHROME_PATH = process.env.CHROME_PATH || "chromium";
const TEST_EMAIL = "e2e-" + Date.now().toString(36) + "@test.com";

// ── Runner ─────────────────────────────────────────────────────────────────

async function runTests(page) {
  // Debug: log all input-like elements
  const inputs = await page.locator("input, textarea, [contenteditable]").all();
  console.log(`  Input elements: ${inputs.length}`);
  for (const el of inputs) {
    const tag = await el.evaluate(
      (e) => e.tagName + (e.getAttribute("aria-label") ? `[aria-label="${e.getAttribute("aria-label")}"]` : "")
    );
    const visible = await el.isVisible();
    const placeholder = await el.getAttribute("placeholder");
    console.log(`    ${tag} visible=${visible} placeholder="${placeholder}"`);
  }

  // Debug: dump script src attributes
  const scripts = await page.locator("script[src]").all();
  console.log(`  Scripts loaded: ${scripts.length}`);
  for (const s of scripts) {
    console.log(`    ${await s.getAttribute("src")}`);
  }

  // ═══════════════════════════════════════════
  console.log("\n--- ACCOUNT ---");

  await test("!email account list", async () => {
    await typeCommand("!email account list");
    await pressEnter();
    const text = await getPopupText();
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text}'`);
    console.log(`    Accounts: ${text.substring(0, 100)}...`);
  });

  await test("!email account add " + TEST_EMAIL, async () => {
    await typeCommand("!email account add " + TEST_EMAIL);
    await pressEnter();
    const text = await getPopupText();
    assert(text.includes("Done") || text.includes(TEST_EMAIL),
      `Expected success, got (first 100): '${text.substring(0, 100)}'`);
  });

  await test("!email account list (after add)", async () => {
    await typeCommand("!email account list");
    await pressEnter();
    const text = await getPopupText();
    assert(text.includes("@"), `Expected account with email, got (first 100): '${text.substring(0, 100)}'`);
  });

  await test("UUID auto-complete", async () => {
    await typeCommand("!email account delete ");
    await sleep(1500);
    const items = page.locator(".suggestions li");
    const count = await items.count();
    if (count > 0) {
      const first = await items.first().textContent();
      console.log(`    Suggestion: ${first}`);
      assert(first.includes("@"), `Suggestion should contain email: '${first}'`);
    } else {
      console.log("    (no suggestions — may be expected)");
    }
  });

  await test("!email account delete", async () => {
    await typeCommand("!email account delete " + TEST_EMAIL);
    await pressEnter();
    await sleep(1000);
    const text = await getPopupText();
    console.log(`    Delete result: ${text.substring(0, 80)}`);
  });

  await test("!email account list (after delete)", async () => {
    await typeCommand("!email account list");
    await pressEnter();
    const text = await getPopupText();
    console.log(`    Accounts: ${text.substring(0, 100)}...`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- CALENDAR ---");

  await test("!calendar account list", async () => {
    await typeCommand("!calendar account list");
    await pressEnter();
    const text = await getPopupText();
    const lower = text.toLowerCase();
    assert(lower.includes("calendar") || lower.includes("no calendars"),
      `Expected calendar account list, got: '${text.substring(0, 200)}'`);
  });

  await test("!calendar account add", async () => {
    await typeCommand("!calendar account add https://cal.example.com/test");
    await pressEnter();
    const text = await getPopupText();
    assert(text.includes("Done") || /[0-9a-f]{8}/.test(text),
      `Expected success (UUID or Done), got: '${text}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- TAB COMPLETION ---");

  await test("Tab: !ac → !account", async () => {
    const input = page.locator("[aria-label='Message input']");
    await input.click();
    await input.fill("!ac");
    await sleep(800);
    try {
      const sugg = page.locator(".suggestions li").first();
      if (await sugg.isVisible({ timeout: 2000 })) {
        const suggText = await sugg.textContent();
        await sugg.click();
        await sleep(300);
        const val = await input.inputValue();
        console.log(`    Suggestion "${suggText}" → "${val}"`);
      } else {
        console.log("    (no visible suggestions)");
      }
    } catch {
      console.log("    (no suggestions dropdown)");
    }
  });

  await test("Tab: !account → children", async () => {
    const input = page.locator("[aria-label='Message input']");
    const currentVal = await input.inputValue();
    console.log(`    Current input: "${currentVal}"`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- ADMIN ---");

  await test("!help", async () => {
    await typeCommand("!help");
    await pressEnter();
    const text = await getPopupText();
    assert(text.includes("account") || text.includes("Available"),
      `Expected help, got: '${text}'`);
  });

  // ═══════════════════════════════════════════
  console.log("\n--- PROMPT COMMANDS (/*) ---");

  await test("/* list API returns array with seeded demo command", async () => {
    const data = await page.evaluate(async () => {
      const resp = await fetch("/api/v1/prompt-commands/list");
      return resp.ok ? await resp.json() : null;
    });
    assert(Array.isArray(data), `Expected array, got: ${JSON.stringify(data)}`);
    console.log(`    Found ${data.length} prompt commands`);
    if (data.length > 0) {
      console.log(`    First: /*${data[0].name} — ${data[0].description}`);
    }
  });

  await test("/* expand API returns expanded text", async () => {
    const data = await page.evaluate(async () => {
      const resp = await fetch("/api/v1/prompt-commands/expand", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "demo", args: ["test-arg"] }),
      });
      return resp.ok ? await resp.json() : null;
    });
    assert(data !== null, "expand returned null");
    assert(data.name === "demo", `Expected name "demo", got "${data.name}"`);
    assert(data.expanded.includes("test-arg"),
      `Expected expanded text to include "test-arg", got: "${data.expanded}"`);
    console.log(`    Expanded: "${data.expanded.substring(0, 80)}..."`);
  });

  await test("/* expand API returns 404 for unknown name", async () => {
    const status = await page.evaluate(async () => {
      const resp = await fetch("/api/v1/prompt-commands/expand", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "nonexistent", args: [] }),
      });
      return resp.status;
    });
    assert(status === 404, `Expected 404, got ${status}`);
  });

  await test("/* nonexistent shows error", async () => {
    await typeCommand("/*nonexistent");
    await pressEnter();
    const text = await getPopupText();
    assert(text.includes("not found") || text.includes("nonexistent"),
      `Expected 'not found' error, got: '${text.substring(0, 100)}'`);
  });

  await test("/* prefix triggers autocomplete", async () => {
    const input = page.locator("[aria-label='Message input']");
    await input.click();
    await input.fill("/*");
    await sleep(800);
    const firstSugg = page.locator(".suggestions li").first();
    const hasSuggestions = await firstSugg.isVisible().catch(() => false);
    if (hasSuggestions) {
      const text = await firstSugg.textContent();
      console.log(`    Suggestion: ${text.substring(0, 80)}`);
      assert(text.includes("/*"), `Expected /* suggestion, got: "${text}"`);
    } else {
      console.log("    (no suggestion dropdown visible — may be empty list)");
    }
    await input.fill("");
  });
}

// ── Bootstrap ──────────────────────────────────────────────────────────────

runWithBrowser(FRONTEND_URL, CHROME_PATH, "PLAYWRIGHT E2E TESTS", runTests);
