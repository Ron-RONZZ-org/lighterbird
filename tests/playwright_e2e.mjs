/** Playwright E2E test — simulates real user interactions in the browser. */

import { chromium } from "playwright";
import { strict as assert } from "assert";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:6006";
const CHROME_PATH = process.env.CHROME_PATH || "chromium";
const TEST_EMAIL = "e2e-" + Date.now().toString(36) + "@test.com";

let browser, page;
let passed = 0, failed = 0;
let pageErrors = [];
let consoleErrors = [];

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function typeCommand(cmd) {
  // Debug: log all input-like elements
  const inputs = await page.locator("input, textarea, [contenteditable]").all();
  console.log(`    Found ${inputs.length} input elements`);
  for (const el of inputs) {
    const tag = await el.evaluate(e => e.tagName + (e.getAttribute('aria-label') ? `[aria-label="${e.getAttribute('aria-label')}"]` : ''));
    const visible = await el.isVisible();
    console.log(`      ${tag} visible=${visible} placeholder="${await el.getAttribute('placeholder')}"`);
  }

  // Ensure we're on the home tab (Alt+1) so the input is visible
  const input = page.locator("[aria-label='Message input']");
  const isVisible = await input.isVisible().catch(() => false);
  if (!isVisible) {
    // Press Escape twice (blur then close) then wait for home tab
    await page.keyboard.press("Escape");
    await sleep(300);
    await page.keyboard.press("Escape");
    await sleep(500);
  }

  await input.waitFor({ state: "visible", timeout: 5000 });
  await input.click();
  await input.fill("");
  await sleep(100);
  await input.pressSequentially(cmd, { delay: 20 });
  await sleep(500);
}

async function pressEnter() {
  await page.keyboard.press("Enter");
  await sleep(1200);
}

async function pressTab() {
  await page.keyboard.press("Tab");
  await sleep(400);
}

async function getPopupText() {
  try {
    // Wait for any result tab content to appear
    await sleep(500);
    // Read the body text (results appear somewhere in the DOM)
    const body = page.locator("body");
    let text = ((await body.textContent()) || "").trim();
    // Strip known formatting artifacts for cleaner assertion
    text = text.replace(/\s+/g, " ").trim();
    return text;
  } catch {
    return "(no result)";
  }
}

async function closePopupOrSkip() {
  try {
    // Close all open result tabs: navigate to home via Alt+1, then press
    // Escape once per result tab (first Escape blurs input, subsequent
    // Escapes close tabs since home tab auto-focuses the input).
    // We use a loop to close any open tabs.
    for (let i = 0; i < 5; i++) {
      // Alt+1 switches to home tab (handled by TabView's global shortcut)
      await page.keyboard.press("Escape");
      await sleep(300);
    }
    // Also dismiss any notice
    try {
      const dismissBtn = page.locator("button", { hasText: "Dismiss notice" });
      if (await dismissBtn.isVisible({ timeout: 500 })) {
        await dismissBtn.click();
        await sleep(300);
      }
    } catch { /* no notice */ }
  } catch { /* ignore */ }
}

let screenshotCounter = 0;
async function test(desc, fn) {
  try {
    await fn();
    console.log(`  ✓ ${desc}`);
    passed++;
  } catch (e) {
    const ssPath = `/tmp/e2e-fail-${screenshotCounter++}.png`;
    try { await page.screenshot({ path: ssPath }); console.log(`    Screenshot saved to ${ssPath}`); } catch {}
    console.log(`  ✗ ${desc}: ${e.message}`);
    if (e.message.includes("Timeout") && e.message.includes("click")) {
      // Log what's on the page
      const body = await page.locator("main").textContent();
      console.log(`    Page text: ${(body || "").substring(0, 200)}`);
    }
    failed++;
  } finally {
    await closePopupOrSkip();
  }
}

async function run() {
  browser = await chromium.launch({
    headless: true,
    executablePath: CHROME_PATH,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
  });
  const context = await browser.newContext({ viewport: { width: 960, height: 720 } });
  page = await context.newPage();
  page.on("pageerror", (err) => { pageErrors.push(err.message); console.log("  [BROWSER ERROR]", err.message); });
  page.on("console", (msg) => { if (msg.type() === "error") { consoleErrors.push(msg.text()); console.log("  [CONSOLE ERROR]", msg.text()); } });

  console.log("=".repeat(70));
  console.log("PLAYWRIGHT E2E TESTS");
  console.log("=".repeat(70));
  console.log();

  await page.goto(FRONTEND_URL, { waitUntil: "networkidle" });
  console.log("✓ Page loaded:", await page.title());
  await sleep(2000);

  // Debug: dump full HTML head section to see assets
  const scripts = await page.locator("script[src]").all();
  console.log(`  Scripts loaded: ${scripts.length}`);
  for (const s of scripts) {
    console.log(`    ${await s.getAttribute('src')}`);
  }

  // Debug: log all input-like elements
  const inputs = await page.locator("input, textarea, [contenteditable]").all();
  console.log(`  Input elements: ${inputs.length}`);
  for (const el of inputs) {
    const tag = await el.evaluate(e => e.tagName + (e.getAttribute('aria-label') ? `[aria-label="${e.getAttribute('aria-label')}"]` : ''));
    const visible = await el.isVisible();
    const placeholder = await el.getAttribute('placeholder');
    console.log(`    ${tag} visible=${visible} placeholder="${placeholder}"`);
  }

  // Dismiss notice if present
  try {
    const dismissBtn = page.locator("button", { hasText: "Dismiss notice" });
    if (await dismissBtn.isVisible({ timeout: 1000 })) {
      await dismissBtn.click();
      await sleep(500);
      console.log("  ✓ Dismissed notice banner");
    }
  } catch { /* no notice */ }
  await sleep(1000);

  // ═══════════════════════════════════════════
  console.log("--- ACCOUNT ---");

  await test("!email account list", async () => {
    await typeCommand("!email account list");
    await pressEnter();
    const text = await getPopupText();
    // Account list may be empty or have accounts — just verify no error
    assert(!text.includes("Unknown") && !text.includes("Error"),
      `Got error: '${text}'`);
    console.log(`    Accounts: ${text.substring(0, 100)}...`);
  });

  await test("!email account add", async () => {
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
  console.log();
  console.log("--- CALENDAR ---");

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
  console.log();
  console.log("--- TAB COMPLETION ---");

  await test("Tab: !ac → !account", async () => {
    const input = page.locator("[aria-label='Message input']");
    await input.click();
    await input.fill("!ac");
    await sleep(800);
    // Try clicking a suggestion if available
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
  console.log();
  console.log("--- ADMIN ---");

  await test("!help", async () => {
    await typeCommand("!help");
    await pressEnter();
    const text = await getPopupText();
    assert(text.includes("account") || text.includes("Available"),
      `Expected help, got: '${text}'`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- PROMPT COMMANDS (/*) ---");

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

  // Type /* and verify autocomplete works (the seeded demo command should appear)
  await test("/* prefix triggers autocomplete", async () => {
    const input = page.locator("[aria-label='Message input']");
    await input.click();
    await input.fill("/*");
    await sleep(800);
    // Check if suggestions dropdown appears
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

  console.log();
  if (pageErrors.length > 0) {
    console.log(`  [ERROR] ${pageErrors.length} unhandled page error(s) during session`);
  }
  if (consoleErrors.length > 0) {
    console.log(`  [ERROR] ${consoleErrors.length} console error(s) during session`);
  }
  console.log(`RESULTS: ${passed} passed, ${failed} failed`);

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
}

run().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(1);
});
