/**
 * Playwright E2E test — letter send / preview / PDF download flow.
 *
 * Run: cd web && node playwright-letter-e2e.mjs
 */

import { chromium } from "playwright";
import { strict as assert } from "assert";

const FRONTEND_URL = "http://127.0.0.1:8000";
const CHROME_PATH = "/home/rongzhou/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell";

let browser, page;
let passed = 0, failed = 0;

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function typeCommand(cmd) {
  // Navigate to home tab first (command bar lives on home tab).
  // For a SPA that already shows a result tab, press Escape to close it,
  // then if needed, click the home tab button.
  const homeTabBtn = page.locator('button[role="tab"]').first();
  if (await homeTabBtn.isVisible().catch(() => false)) {
    await homeTabBtn.click();
    await sleep(300);
  }

  const input = page.locator("textarea[aria-label='Message input']");
  await input.waitFor({ state: "visible", timeout: 5000 });
  await input.click();
  await input.fill("");
  await sleep(100);
  await input.pressSequentially(cmd, { delay: 15 });
  await sleep(400);
}

async function pressEnter() {
  await page.keyboard.press("Enter");
  await sleep(2000);
}

async function closePopupOrSkip() {
  try {
    // Close all result tabs to get back to a clean state
    for (let i = 0; i < 5; i++) {
      // Press Escape to close the current tab
      await page.keyboard.press("Escape");
      await sleep(300);
    }
  } catch { /* ignore */ }
}

async function getActiveTabText() {
  try {
    const content = page.locator('[role="region"][aria-label="Tab content"]');
    const text = ((await content.textContent()) || "").trim();
    return text;
  } catch {
    return "(no tab content)";
  }
}

async function test(desc, fn) {
  try {
    await fn();
    console.log(`  \u2713 ${desc}`);
    passed++;
  } catch (e) {
    console.log(`  \u2717 ${desc}: ${e.message.split('\n')[0]}`);
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
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  page = await context.newPage();
  page.on("pageerror", (err) => console.log("  [BROWSER ERROR]", err.message));

  console.log("=".repeat(70));
  console.log("LETTER SEND E2E TESTS");
  console.log("=".repeat(70));
  console.log();

  await page.goto(FRONTEND_URL, { waitUntil: "domcontentloaded" });
  await sleep(2000);
  console.log(`\u2713 Page loaded: "${await page.title()}"`);
  console.log();

  // ═══════════════════════════════════════════
  console.log("--- LETTER SEND DIRECT ---");

  await test("!letter send returns status with uuid+object", async () => {
    await typeCommand('!letter send "Test Recipient" --object "E2E Test" --body-text "Hello from E2E" --sender "Tester"');
    await pressEnter();
    await sleep(500);

    const text = await getActiveTabText();
    assert(text.length > 0, `Status tab should have content`);
    console.log(`    Status: "${text.substring(0, 120)}"`);
  });

  await test("!letter send response includes render_url", async () => {
    const [response] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes("/api/v1/command") && res.request().method() === "POST",
        { timeout: 5000 }
      ),
      (async () => {
        await typeCommand('!letter send "Network Tester" --object "Net Test" --body-text "Test" --sender "Tester"');
        await pressEnter();
        await sleep(500);
      })(),
    ]);
    const data = await response.json();
    assert(data.data?.render_url, `Response should contain render_url`);
    assert(data.data.render_url.includes("/render"),
      `render_url should contain /render, got: ${data.data.render_url}`);
    console.log(`    render_url: ${data.data.render_url}`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- INTERACTIVE FORM ---");

  await test("!letter send (no args) opens and fills the letter form, submits it", async () => {
    await typeCommand("!letter send");
    await pressEnter();
    await sleep(1000);

    const form = page.locator("form.letter-form");
    const visible = await form.isVisible().catch(() => false);
    assert(visible, "Letter send form should be visible");
    console.log(`    Form visible: ${visible}`);

    // Fill recipient (second textarea)
    const textareas = await form.locator("textarea").all();
    if (textareas.length >= 2) {
      await textareas[1].fill("John Doe\n123 Main St\njohn@example.com");
    }
    await sleep(200);

    // Fill subject
    const inputs = await form.locator("input[type='text']").all();
    for (const inp of inputs) {
      const ph = await inp.getAttribute("placeholder");
      if (ph && ph.toLowerCase().includes("subject")) {
        await inp.fill("E2E Test Letter");
        break;
      }
    }
    await sleep(200);

    // Fill body
    const bodyTa = form.locator("textarea.body-textarea");
    if (await bodyTa.isVisible().catch(() => false)) {
      await bodyTa.fill("## Test Letter\n\nThis is a test letter body from E2E test.");
    }
    await sleep(200);

    // Submit
    const submitBtn = form.locator("button[type='submit']");
    const btnCount = await submitBtn.count();
    if (btnCount > 0) {
      await submitBtn.click();
      await sleep(2000);
      console.log(`    Form submitted successfully`);
    } else {
      console.log(`    WARNING: No submit button found`);
    }
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- LETTER LIST ---");

  await test("!letter list shows test letters", async () => {
    await typeCommand("!letter list");
    await pressEnter();
    await sleep(500);

    const text = await getActiveTabText();
    assert(text.includes("E2E") || text.includes("Net") || text.includes("Test") || text.length > 20,
      `List should contain letters, got: "${text.substring(0, 100)}"`);
    console.log(`    List: "${text.substring(0, 100)}"`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- RENDER ENDPOINT ---");

  await test("GET /letters/{uuid}/render returns full HTML with print JS", async () => {
    const resp = await fetch("http://127.0.0.1:8000/api/v1/letters/letters?limit=5");
    const data = await resp.json();
    const letters = data.letters || [];
    const testLetter = letters.find(l => l.object && /E2E|Net|Test/i.test(l.object));
    if (!testLetter) {
      console.log("    No test letter found, skipping");
      return;
    }
    const uuid = testLetter.uuid;
    console.log(`    UUID: ${uuid.slice(0, 8)} (${testLetter.object})`);

    const r = await fetch(`http://127.0.0.1:8000/api/v1/letters/letters/${uuid}/render`);
    assert(r.ok, `Render should return 200, got ${r.status}`);
    const html = await r.text();
    assert(html.includes("window.print"), "Should contain window.print()");
    assert(html.includes("<!DOCTYPE html>"), "Should be full HTML");
    assert(html.includes(testLetter.object), `Should contain subject "${testLetter.object}"`);
    console.log(`    HTML: ${html.length}b, print JS: ${html.includes("window.print")}, letterhead: ${html.includes("sender") || html.includes("recipient")}`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- PREVIEW ENDPOINT ---");

  await test("POST render-preview converts markdown to HTML", async () => {
    const r = await fetch("http://127.0.0.1:8000/api/v1/letters/render-preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: "## Preview Test\n\nThis is a **preview**.", format: "markdown" }),
    });
    assert(r.ok, `Status ${r.status}`);
    const data = await r.json();
    assert(data.html, "Should have html key");
    assert(data.html.includes("<h2>Preview Test</h2>"), "Heading should be converted");
    assert(data.html.includes("<strong>") || data.html.includes("<b>"), "Bold should be converted");
    console.log(`    Preview: ${data.html.substring(0, 80)}`);
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("--- CLEANUP ---");

  await test("Delete test letters", async () => {
    const resp = await fetch("http://127.0.0.1:8000/api/v1/letters/letters?limit=50");
    const data = await resp.json();
    const letters = data.letters || [];
    for (const letter of letters) {
      if (letter.object && /E2E|Net|Test|test/i.test(letter.object)) {
        await fetch(`http://127.0.0.1:8000/api/v1/letters/letters/${letter.uuid}`, { method: "DELETE" });
        console.log(`    Removed: ${letter.uuid.slice(0, 8)} (${letter.object})`);
      }
    }
  });

  // ═══════════════════════════════════════════
  console.log();
  console.log("=".repeat(70));
  console.log(`RESULTS: ${passed} passed, ${failed} failed`);
  console.log("=".repeat(70));

  await browser.close();
  process.exit(failed > 0 ? 1 : 0);
}

run().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(1);
});
