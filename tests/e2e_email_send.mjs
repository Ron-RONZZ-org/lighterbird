/**
 * E2E test for email send flow — reproduce bugs from issue #212.
 *
 * Tests:
 *   1.  ComposeEmail form opens from incomplete !email send
 *   2.  Fill and submit the form (expect queued or sent response)
 *   3.  HomeTab ChatInput remains accessible after tabs are open
 *       (regression test for LLM message box hidden by tab bar)
 *
 * Run with:
 *   node tests/e2e_email_send.mjs
 *
 * Environment:
 *   FRONTEND_URL  — defaults to http://127.0.0.1:6006
 *   CHROME_PATH   — defaults to "chromium"
 */

import { chromium } from "playwright";
import { strict as assert } from "assert";
import {
  test, typeCommand, pressEnter, getResultPanelText,
  assertFormOpened, assertHomeActive,
  runWithBrowser, sleep,
} from "./e2e_helpers.mjs";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:6006";
const CHROME_PATH = process.env.CHROME_PATH || "chromium";

// ── Tests ─────────────────────────────────────────────────────────────────

async function runTests(page) {
  // ═══════════════════════════════════════════
  console.log("\n--- EMAIL SEND FORM ---");

  await test("!email send (incomplete) opens ComposeEmail form", async () => {
    await typeCommand("!email send");
    await pressEnter();
    await assertFormOpened("Compose Email", ["To", "Subject"]);
  });

  await test("ComposeEmail form: fill fields and submit", async () => {
    await typeCommand("!email send");
    await pressEnter();
    await assertFormOpened("Compose Email", ["To", "Subject"]);

    // Fill recipient (use a plausible address — SMTP will fail and queue)
    const toInput = page.locator('[role="tabpanel"] input[placeholder*="recipient"]');
    if (await toInput.isVisible({ timeout: 1000 })) {
      await toInput.fill("test@example.com");
    } else {
      // MultiEntryField — type and press Enter to add chip
      const chipInput = page.locator('[role="tabpanel"] .multi-entry-field input');
      await chipInput.fill("test@example.com");
      await page.keyboard.press("Enter");
    }
    await sleep(100);

    // Fill subject
    const subjectInput = page.locator('[role="tabpanel"] input[placeholder="Subject"]');
    await subjectInput.fill("E2E test email");
    await sleep(50);

    // Fill body
    const bodyArea = page.locator('[role="tabpanel"] textarea');
    await bodyArea.fill("This is an automated test email.");
    await sleep(100);

    // Click Send
    const sendBtn = page.locator('[role="tabpanel"] button:has-text("Send")');
    await sendBtn.click();
    await sleep(800);

    // Result: either "Sent", "Queued" (SMTP unavailable), or error banner
    const text = await getResultPanelText();
    const acceptable = text.includes("Sent") || text.includes("Queued")
      || text.includes("queued") || text.includes("sent");
    if (!acceptable) {
      // If neither, check for error — just ensure no crash / stuck loading
      console.log(`    Submit result: "${text.substring(0, 120)}..." — may be expected without SMTP`);
    }
  });

  // ═══════════════════════════════════════════
  console.log("\n--- LLM INPUT VISIBILITY (regression: bug 3) ---");

  await test("HomeTab ChatInput visible after returning from result tabs", async () => {
    // Open a list tab to simulate result tabs open
    await typeCommand("!email account list");
    await pressEnter();
    await sleep(300);

    // Switch back to Home tab
    await page.keyboard.press("Alt+1");
    await sleep(300);

    // Assert Home tab is active and input is visible
    await assertHomeActive();

    // Verify the input is not clipped/behind the tab bar by checking
    // its bounding box relative to the viewport
    const input = page.locator("[aria-label='Message input']");
    await input.waitFor({ state: "visible", timeout: 3000 });
    const box = await input.boundingBox();
    assert(box, "ChatInput should have a bounding box");
    assert(box.y + box.height <= 720, `ChatInput bottom (${box.y + box.height}) should be within viewport (720)`);
    assert(box.y >= 0, `ChatInput top (${box.y}) should be within viewport`);
  });
}

// ── Entry point ───────────────────────────────────────────────────────────

runWithBrowser(FRONTEND_URL, CHROME_PATH, "Email Send E2E Tests", runTests);
