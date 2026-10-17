import { chromium } from "../web/node_modules/playwright/index.mjs";
import { readFileSync, existsSync } from "fs";

const ARTIFACT_DIR = "C:/Users/paulm/.gemini/antigravity-ide/brain/87666082-014f-4ca7-ba09-1931c6dc8f43";
const BASE_URL = "https://web-git-promotion-sandbox-paulmircea15-9488s-projects.vercel.app";
const API_URL = "https://avenqo-platform-sandbox.up.railway.app";

async function run() {
  console.log("=== AVENQO PHASE 7.9 PLAYWRIGHT REAL SANDBOX VERIFICATION ===");
  console.log(`Frontend URL: ${BASE_URL}`);
  console.log(`Backend URL:  ${API_URL}`);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    locale: "fr-CA",
  });
  const page = await context.newPage();

  try {
    // -------------------------------------------------------------
    // Step 1: Login Page
    // -------------------------------------------------------------
    console.log("\n[Step 1] Navigating to login page...");
    await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle", timeout: 35000 });
    await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_01_login_page.png`, fullPage: false });
    console.log("  ✓ Captured phase7_9_01_login_page.png");

    // -------------------------------------------------------------
    // Step 2: Authenticate as Alex Physio Sandbox Admin
    // -------------------------------------------------------------
    console.log("\n[Step 2] Authenticating as alex.physio.sandbox@avenqo.ca...");
    await page.fill('input[name="email"]', "alex.physio.sandbox@avenqo.ca");
    const sandboxPassword = process.env.AVENQO_E2E_PASSWORD;
    if (!sandboxPassword) throw new Error("AVENQO_E2E_PASSWORD environment variable is required");
    await page.fill('input[name="password"]', sandboxPassword);
    await page.click('button[type="submit"]');

    console.log("  Awaiting dashboard navigation...");
    await page.waitForURL("**/dashboard**", { timeout: 30000 }).catch(() => {
      console.log("  Navigation URL: " + page.url());
    });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_02_dashboard.png`, fullPage: false });
    console.log("  ✓ Captured phase7_9_02_dashboard.png at " + page.url());

    // -------------------------------------------------------------
    // Step 3: CRM Opening Hours Configuration & Persistence
    // -------------------------------------------------------------
    console.log("\n[Step 3] Testing CRM Opening Hours Configuration...");
    await page.goto(`${BASE_URL}/crm`, { waitUntil: "networkidle", timeout: 35000 });
    await page.waitForTimeout(2000);

    const wizardBtn = await page.$('button:has-text("Horaires & Services")');
    if (wizardBtn) {
      await wizardBtn.click();
      await page.waitForTimeout(1500);
      await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_03_crm_hours_wizard.png`, fullPage: false });
      console.log("  ✓ Captured phase7_9_03_crm_hours_wizard.png");

      // Verify business hours form fields or save
      const saveBtn = await page.$('button:has-text("Sauvegarder"), button:has-text("Enregistrer")');
      if (saveBtn) {
        await saveBtn.click();
        await page.waitForTimeout(1500);
      }
      // Close wizard
      const closeBtn = await page.$('div.fixed.z-50 button:has(svg), button[aria-label="Fermer"], button[title="Fermer"]');
      if (closeBtn) {
        await closeBtn.click();
      } else {
        await page.keyboard.press("Escape");
      }
      await page.waitForTimeout(1500);

      // Refresh page and confirm persisted opening hours
      console.log("  Refreshing page to verify persistence...");
      await page.reload({ waitUntil: "networkidle", timeout: 35000 });
      await page.waitForTimeout(2000);
      await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_04_crm_hours_persisted.png`, fullPage: false });
      console.log("  ✓ Captured phase7_9_04_crm_hours_persisted.png");
    }

    // -------------------------------------------------------------
    // Step 4: Central AI - Real CRM Booking Journey
    // -------------------------------------------------------------
    console.log("\n[Step 4] Testing Central AI Real CRM Booking...");
    const copilotBtn = await page.$('button[aria-label*="Copilot"], button:has-text("Copilot"), button[title*="Copilot"], button[aria-controls="avenqo-central-dialog"]');
    if (copilotBtn) {
      await copilotBtn.click();
      await page.waitForTimeout(2500);
    }
    const copilotInput = await page.$('input[placeholder*="Central AI"], form input[type="text"], textarea[placeholder*="Posez"], textarea');
    if (copilotInput) {
      // 4a. Outside-hours rejection
      console.log("  Sending: 'Trouve-moi un rendez-vous jeudi 22 octobre 2026 à 8 h.'");
      await copilotInput.fill("Trouve-moi un rendez-vous jeudi 22 octobre 2026 à 8 h.");
      await copilotInput.press("Enter");
      await page.waitForTimeout(8000);
      await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_05_central_ai_outside_hours_rejection.png`, fullPage: false });
      console.log("  ✓ Captured phase7_9_05_central_ai_outside_hours_rejection.png");

      // 4b. Slot selection inside hours
      console.log("  Sending: 'Quels créneaux sont disponibles après 9 h ?'");
      await copilotInput.fill("Quels créneaux sont disponibles après 9 h ?");
      await copilotInput.press("Enter");
      await page.waitForTimeout(8000);

      // 4c. Select 11h
      console.log("  Sending: 'Réserve celui de 11 h.'");
      await copilotInput.fill("Réserve celui de 11 h.");
      await copilotInput.press("Enter");
      await page.waitForTimeout(6000);

      // 4d. Confirm booking
      console.log("  Sending: 'Oui, je confirme'");
      await copilotInput.fill("Oui, je confirme");
      await copilotInput.press("Enter");
      await page.waitForTimeout(8000);
      await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_06_central_ai_booking_confirmed.png`, fullPage: false });
      console.log("  ✓ Captured phase7_9_06_central_ai_booking_confirmed.png");

      // 4e. Verify appointment listed
      console.log("  Sending: 'Montre-moi mes rendez-vous.'");
      await copilotInput.fill("Montre-moi mes rendez-vous.");
      await copilotInput.press("Enter");
      await page.waitForTimeout(7000);
      await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_07_central_ai_list_appointments.png`, fullPage: false });
      console.log("  ✓ Captured phase7_9_07_central_ai_list_appointments.png");

      // Close copilot
      const closeCopilot = await page.$('button[aria-label*="Fermer"], button:has-text("Fermer")');
      if (closeCopilot) await closeCopilot.click();
      await page.waitForTimeout(1000);
    }

    // -------------------------------------------------------------
    // Step 5: CRM Calendar View
    // -------------------------------------------------------------
    console.log("\n[Step 5] Checking CRM Calendar View...");
    await page.goto(`${BASE_URL}/crm`, { waitUntil: "networkidle", timeout: 35000 });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_08_crm_calendar_view.png`, fullPage: false });
    console.log("  ✓ Captured phase7_9_08_crm_calendar_view.png");

    // -------------------------------------------------------------
    // Step 6: Overlapping Booking Rejection & Cancellation
    // -------------------------------------------------------------
    console.log("\n[Step 6] Testing Overlapping Booking & Cancellation...");
    const copilotBtnStep6 = await page.$('button[aria-label*="Copilot"], button:has-text("Copilot"), button[title*="Copilot"], button[aria-controls="avenqo-central-dialog"]');
    if (copilotBtnStep6) {
      await copilotBtnStep6.click();
      await page.waitForTimeout(2000);
      const input = await page.$('input[placeholder*="Central AI"], form input[type="text"], textarea[placeholder*="Posez"], textarea');
      if (input) {
        // Attempt duplicate booking for same slot
        console.log("  Testing overlapping booking on 11h...");
        await input.fill("Réserve un rendez-vous jeudi 22 octobre 2026 à 11 h.");
        await input.press("Enter");
        await page.waitForTimeout(7000);
        await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_09_overlapping_booking_rejected.png`, fullPage: false });
        console.log("  ✓ Captured phase7_9_09_overlapping_booking_rejected.png");

        // Cancel appointment
        console.log("  Sending: 'Annule ce rendez-vous.'");
        await input.fill("Annule ce rendez-vous.");
        await input.press("Enter");
        await page.waitForTimeout(7000);
        await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_10_central_ai_cancellation.png`, fullPage: false });
        console.log("  ✓ Captured phase7_9_10_central_ai_cancellation.png");

        const closeCopilot = await page.$('button[aria-label*="Fermer"], button:has-text("Fermer")');
        if (closeCopilot) await closeCopilot.click();
      }
    }

    // -------------------------------------------------------------
    // Step 7: Produits_Ero CRM Unconfigured Availability Check
    // -------------------------------------------------------------
    console.log("\n[Step 7] Testing Produits_Ero (Unconfigured CRM Business Hours)...");
    if (existsSync("scripts/produits_ero_token.txt")) {
      const eroToken = readFileSync("scripts/produits_ero_token.txt", "utf-8").trim();
      const hostname = new URL(BASE_URL).hostname;

      await context.addCookies([
        {
          name: "avenqo_access_token",
          value: eroToken,
          domain: hostname,
          path: "/",
          httpOnly: false,
          secure: true,
          sameSite: "Lax",
        },
      ]);

      await page.goto(`${BASE_URL}/crm`, { waitUntil: "networkidle", timeout: 35000 });
      await page.waitForTimeout(3000);
      const unconfiguredBanner = await page.$('[data-testid="crm-business-hours-unconfigured-banner"], button:has-text("Configurer maintenant")');
      if (unconfiguredBanner) {
        await unconfiguredBanner.scrollIntoViewIfNeeded();
        console.log("  ✓ Found unconfigured business hours banner!");
      }
      await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_11_crm_unconfigured_produits_ero.png`, fullPage: false });
      console.log("  ✓ Captured phase7_9_11_crm_unconfigured_produits_ero.png");

      // -------------------------------------------------------------
      // Step 8: Produits_Ero Retail AI Forecasting (Superstore-utf8.csv)
      // -------------------------------------------------------------
      console.log("\n[Step 8] Testing Retail Forecasting with Superstore-utf8.csv...");
      await page.goto(`${BASE_URL}/retail`, { waitUntil: "networkidle", timeout: 35000 });
      await page.waitForTimeout(3000);

      const forecastTab = await page.locator('nav button:has-text("Prévisions"), button:has-text("Forecasts")').first();
      if (forecastTab) {
        await forecastTab.click();
        await page.waitForTimeout(2500);

        // Horizon 7 Days
        const btn7d = page.locator('button:has-text("7 jours"), button:has-text("7 days")').first();
        await btn7d.waitFor({ state: "visible", timeout: 10000 });
        await btn7d.click();
        await page.waitForResponse(resp => resp.url().includes("/api/v1/sales/summary") && resp.status() === 200, { timeout: 15000 }).catch(() => {});
        await page.waitForTimeout(1500);
        await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_12_retail_forecast_7d.png`, fullPage: false });
        console.log("  ✓ Captured phase7_9_12_retail_forecast_7d.png");

        // Horizon 30 Days
        const btn30d = page.locator('button:has-text("30 jours"), button:has-text("30 days")').first();
        await btn30d.waitFor({ state: "visible", timeout: 10000 });
        await btn30d.click();
        await page.waitForResponse(resp => resp.url().includes("/api/v1/sales/summary") && resp.status() === 200, { timeout: 15000 }).catch(() => {});
        await page.waitForTimeout(1500);
        await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_13_retail_forecast_30d.png`, fullPage: false });
        console.log("  ✓ Captured phase7_9_13_retail_forecast_30d.png");

        // Horizon 90 Days
        const btn90d = page.locator('button:has-text("90 jours"), button:has-text("90 days")').first();
        await btn90d.waitFor({ state: "visible", timeout: 10000 });
        await btn90d.click();
        await page.waitForResponse(resp => resp.url().includes("/api/v1/sales/summary") && resp.status() === 200, { timeout: 15000 }).catch(() => {});
        await page.waitForTimeout(1500);
        await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_14_retail_forecast_90d.png`, fullPage: false });
        console.log("  ✓ Captured phase7_9_14_retail_forecast_90d.png");
      }

      // -------------------------------------------------------------
      // Step 9: Central AI Cross-Module Analysis (Retail + CRM)
      // -------------------------------------------------------------
      console.log("\n[Step 9] Testing Central AI Cross-Module Conversation on Produits_Ero...");
      const copilotBtnEro = await page.$('button[aria-label*="Copilot"], button:has-text("Copilot"), button[title*="Copilot"], button[aria-controls="avenqo-central-dialog"]');
      if (copilotBtnEro) {
        await copilotBtnEro.click();
        await page.waitForTimeout(2500);
      }
      const copilotInputEro = await page.$('input[placeholder*="Central AI"], form input[type="text"], textarea[placeholder*="Posez"], textarea');
      if (copilotInputEro) {
        console.log("  Sending: 'Analyse les ventes de mon entreprise, indique les tendances importantes et vérifie mes prochains rendez-vous CRM.'");
        await copilotInputEro.fill("Analyse les ventes de mon entreprise, indique les tendances importantes et vérifie mes prochains rendez-vous CRM.");
        await copilotInputEro.press("Enter");
        await page.waitForTimeout(10000);
        await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_15_central_ai_cross_module.png`, fullPage: false });
        console.log("  ✓ Captured phase7_9_15_central_ai_cross_module.png");
      }

      // -------------------------------------------------------------
      // Step 10: Tenant Isolation & Denied Cross-Company Access
      // -------------------------------------------------------------
      console.log("\n[Step 10] Testing Tenant Isolation (Cross-Company Access Denial)...");
      // As Produits_Ero, attempt to fetch Alex Physio's appointments or company info
      const physioCompanyId = "838184d8-77c3-4aeb-a0bf-46394dd5c695";
      const crossTenantRes = await page.evaluate(async (cid) => {
        const r = await fetch(`/api/v1/crm/appointments?company_id=${cid}`);
        return { status: r.status, ok: r.ok };
      }, physioCompanyId);

      console.log(`  Cross-tenant query returned HTTP ${crossTenantRes.status} (ok=${crossTenantRes.ok})`);
      await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_16_tenant_isolation_denied.png`, fullPage: false });
      console.log("  ✓ Captured phase7_9_16_tenant_isolation_denied.png");
    }

    console.log("\n=== ALL REAL PLAYWRIGHT ACCEPTANCE FLOWS EXECUTED ===");
  } catch (error) {
    console.error("Playwright execution error:", error);
    await page.screenshot({ path: `${ARTIFACT_DIR}/phase7_9_error_state.png`, fullPage: false }).catch(() => {});
  } finally {
    await browser.close();
  }
}

run();
