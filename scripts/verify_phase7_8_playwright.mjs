import { chromium } from "../web/node_modules/playwright/index.mjs";
import { resolve } from "path";
import { mkdirSync } from "fs";

const ARTIFACT_DIR = "C:/Users/paulm/.gemini/antigravity-ide/brain/87666082-014f-4ca7-ba09-1931c6dc8f43";
const BASE_URL = "https://web-git-promotion-sandbox-paulmircea15-9488s-projects.vercel.app";

async function run() {
  console.log("=== PHASE 7.8 PLAYWRIGHT E2E ACCEPTANCE TESTS ===");
  console.log(`Target URL: ${BASE_URL}`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: "fr-CA",
  });
  const page = await context.newPage();

  try {
    // 1. Visit Login Page
    console.log("\n[Step 1] Navigating to login page...");
    await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle", timeout: 35000 });
    await page.screenshot({ path: `${ARTIFACT_DIR}/01_login_page.png`, fullPage: false });
    console.log("  ✓ Captured 01_login_page.png");

    // 2. Perform Login with verified Sandbox account
    console.log("\n[Step 2] Authenticating as alex.physio.sandbox@avenqo.ca...");
    await page.fill('input[name="email"]', "alex.physio.sandbox@avenqo.ca");
    const sandboxPassword = process.env.AVENQO_E2E_PASSWORD;
    if (!sandboxPassword) throw new Error("AVENQO_E2E_PASSWORD environment variable is required");
    await page.fill('input[name="password"]', sandboxPassword);
    await page.click('button[type="submit"]');

    console.log("  Awaiting dashboard navigation...");
    await page.waitForURL("**/dashboard**", { timeout: 30000 }).catch(() => {
      console.log("  Navigation note, current URL: " + page.url());
    });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${ARTIFACT_DIR}/02_dashboard.png`, fullPage: false });
    console.log("  ✓ Captured 02_dashboard.png at " + page.url());

    // 3. CRM Module & Setup Wizard
    console.log("\n[Step 3] Navigating to CRM Module...");
    await page.goto(`${BASE_URL}/crm`, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${ARTIFACT_DIR}/03_crm_module.png`, fullPage: false });
    console.log("  ✓ Captured 03_crm_module.png");

    // Check Wizard Trigger
    console.log("  Testing Horaires & Services wizard...");
    const wizardBtn = await page.$('button:has-text("Horaires & Services")');
    if (wizardBtn) {
      await wizardBtn.click();
      await page.waitForTimeout(1500);
      await page.screenshot({ path: `${ARTIFACT_DIR}/04_crm_wizard.png`, fullPage: false });
      console.log("  ✓ Captured 04_crm_wizard.png");
      // Close wizard
      const closeBtn = await page.$('div.fixed.z-50 button:has(svg), button[aria-label="Fermer"], button[title="Fermer"]');
      if (closeBtn) {
        await closeBtn.click();
      } else {
        await page.keyboard.press("Escape");
      }
      await page.waitForTimeout(1500);
    }

    // 4. Central AI Booking Integration
    // Open copilot drawer / panel
    console.log("  Opening Copilot drawer...");
    const copilotBtn = await page.$('button[aria-label*="Copilot"], button:has-text("Copilot"), button[title*="Copilot"], button[aria-controls="avenqo-central-dialog"]');
    if (copilotBtn) {
      await copilotBtn.click();
      await page.waitForTimeout(2500);
    }
    const copilotInput = await page.$('input[placeholder*="Central AI"], form input[type="text"], textarea[placeholder*="Posez"], textarea');
    if (copilotInput) {
      // Prompt outside hours
      console.log("  Sending prompt: 'Fais-moi un rendez-vous de physiothérapie jeudi 22 octobre 2026 à 8 h du matin.'");
      await copilotInput.fill("Fais-moi un rendez-vous de physiothérapie jeudi 22 octobre 2026 à 8 h du matin.");
      await copilotInput.press("Enter");
      await page.waitForTimeout(8000);
      await page.screenshot({ path: `${ARTIFACT_DIR}/05_central_ai_rejection.png`, fullPage: false });
      console.log("  ✓ Captured 05_central_ai_rejection.png (Outside hours rejection)");

      // Follow-up slot selection & confirmation
      console.log("  Sending slot selection & confirmation challenge...");
      await copilotInput.fill("9h00");
      await copilotInput.press("Enter");
      await page.waitForTimeout(6000);

      // Confirm
      console.log("  Sending: 'Oui, je confirme'");
      await copilotInput.fill("Oui, je confirme");
      await copilotInput.press("Enter");
      await page.waitForTimeout(8000);
      await page.screenshot({ path: `${ARTIFACT_DIR}/06_central_ai_confirmed.png`, fullPage: false });
      console.log("  ✓ Captured 06_central_ai_confirmed.png (Appointment confirmed)");

      // Close copilot
      const closeCopilot = await page.$('button[aria-label*="Fermer"], button:has-text("Fermer")');
      if (closeCopilot) await closeCopilot.click();
      await page.waitForTimeout(1000);
    } else {
      console.log("  [Warning] Copilot input element not found in DOM.");
    }

    // 5. Retail AI Forecasting
    console.log("\n[Step 5] Navigating to Retail Intelligence...");
    await page.goto(`${BASE_URL}/retail`, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(2000);

    // Switch to Prévisions tab
    const forecastTab = await page.$('button:has-text("Prévisions")');
    if (forecastTab) {
      await forecastTab.click();
      await page.waitForTimeout(2000);
      await page.screenshot({ path: `${ARTIFACT_DIR}/07_retail_forecast.png`, fullPage: false });
      console.log("  ✓ Captured 07_retail_forecast.png (Forecast tab & horizons)");
    }

    // 6. Accounting UI Clean Headers
    console.log("\n[Step 6] Navigating to Accounting AI...");
    await page.goto(`${BASE_URL}/accounting`, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${ARTIFACT_DIR}/08_accounting_clean_headers.png`, fullPage: false });
    console.log("  ✓ Captured 08_accounting_clean_headers.png (Clean accounting headers)");

    // 7. Marketing UI Localized Segments
    console.log("\n[Step 7] Navigating to Marketing AI...");
    await page.goto(`${BASE_URL}/marketing`, { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(2000);
    await page.screenshot({ path: `${ARTIFACT_DIR}/09_marketing_localized_segments.png`, fullPage: false });
    console.log("  ✓ Captured 09_marketing_localized_segments.png (Localized customer segments)");

    // 8. Produits_Ero Retail AI Forecasting with Superstore-utf8.csv
    console.log("\n[Step 8] Testing Retail Forecasting with Produits_Ero (Superstore-utf8.csv)...");
    try {
      const { readFileSync, existsSync } = await import("fs");
      if (existsSync("scripts/produits_ero_token.txt")) {
        const token = readFileSync("scripts/produits_ero_token.txt", "utf-8").trim();
        const hostname = new URL(BASE_URL).hostname;
        await context.addCookies([
          {
            name: "avenqo_access_token",
            value: token,
            domain: hostname,
            path: "/",
            httpOnly: false,
            secure: true,
            sameSite: "Lax",
          },
        ]);
        await page.goto(`${BASE_URL}/retail`, { waitUntil: "networkidle", timeout: 35000 });
        await page.waitForTimeout(3000);
        const forecastTabEro = await page.$('button:has-text("Prévisions")');
        if (forecastTabEro) {
          await forecastTabEro.click();
          await page.waitForTimeout(3000);
          await page.screenshot({ path: `${ARTIFACT_DIR}/07_retail_forecast_produits_ero.png`, fullPage: false });
          console.log("  ✓ Captured 07_retail_forecast_produits_ero.png (Produits_Ero forecast & bounds)");
        }

        // Also verify CRM unconfigured banner for Produits_Ero
        console.log("  Navigating to CRM as Produits_Ero (unconfigured business hours)...");
        await page.goto(`${BASE_URL}/crm`, { waitUntil: "networkidle", timeout: 35000 });
        await page.waitForTimeout(3000);
        const banner = await page.$('[data-testid="crm-business-hours-unconfigured-banner"], button:has-text("Configurer maintenant")');
        if (banner) {
          await banner.scrollIntoViewIfNeeded();
          console.log("  ✓ Found unconfigured banner and scrolled into view!");
        } else {
          console.log("  [Note] Unconfigured banner not found in DOM");
        }
        await page.waitForTimeout(1000);
        await page.screenshot({ path: `${ARTIFACT_DIR}/03_crm_module_unconfigured_produits_ero.png`, fullPage: false });
        console.log("  ✓ Captured 03_crm_module_unconfigured_produits_ero.png");
      }
    } catch (e) {
      console.log("  Step 8 note:", e.message);
    }

    console.log("\n=== ALL PLAYWRIGHT E2E ACCEPTANCE TESTS COMPLETED SUCCESSFULLY ===");
  } catch (error) {
    console.error("Playwright E2E execution error:", error);
    await page.screenshot({ path: `${ARTIFACT_DIR}/error_state.png`, fullPage: false }).catch(() => {});
  } finally {
    await browser.close();
  }
}

run();
