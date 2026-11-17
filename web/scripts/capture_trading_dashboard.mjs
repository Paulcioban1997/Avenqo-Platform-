import { chromium } from "playwright";
import { resolve } from "path";
import { mkdirSync } from "fs";

const ARTIFACTS_DIR = "C:/Users/paulm/.gemini/antigravity/brain/6e8912cb-f352-49f7-aa3d-a8cae8394823";
mkdirSync(ARTIFACTS_DIR, { recursive: true });

function generateCandles() {
  const candles = [];
  const baseTime = Math.floor(Date.now() / 1000) - 100 * 3600;
  let price = 82400.0;

  for (let i = 0; i < 100; i++) {
    const time = baseTime + i * 3600;
    const delta = (Math.sin(i / 5) * 450 + (i * 42)) + (Math.random() * 200 - 100);
    const open = Math.round((price + (i === 99 ? 0 : delta)) * 100) / 100;
    const high = Math.round((open + Math.random() * 300 + 50) * 100) / 100;
    const low = Math.round((open - Math.random() * 250 - 50) * 100) / 100;
    const close = i === 99 ? 86421.50 : Math.round((low + Math.random() * (high - low)) * 100) / 100;
    const volume = Math.round(150 + Math.random() * 450);
    candles.push({ time, open, high, low, close, volume });
    price = close;
  }
  return candles;
}

async function main() {
  console.log("=== DIAGNOSE & CAPTURE AVENQO TRADING AI 2.0 ===");
  const browser = await chromium.launch({ headless: true });

  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1080 },
      locale: "fr-CA",
    });

    const page = await context.newPage();

    page.on("console", (msg) => console.log(`[BROWSER ${msg.type().toUpperCase()}]:`, msg.text()));
    page.on("pageerror", (err) => console.log("[PAGE ERROR]:", err.message));

    await page.route("**/api/v1/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          user: {
            id: "11111111-2222-3333-4444-555555555555",
            first_name: "Paul",
            last_name: "M",
            job_title: "Directeur Général",
            role: "admin",
            permissions: ["trading:read", "trading:write", "trading:admin", "data:read"],
            is_platform_admin: true,
          },
          company: {
            id: "22222222-3333-4444-5555-666666666666",
            name: "Produits Ero",
            subscription_plan: "scale",
            preferred_language: "fr",
            display_currency: "CAD",
            brand_color: "#0076FF",
          },
          organizations: [
            {
              id: "22222222-3333-4444-5555-666666666666",
              name: "Produits Ero",
              slug: "produits-ero",
              subscription_plan: "scale",
              role: "admin",
              is_current: true,
            },
          ],
        }),
      });
    });

    await page.route("**/api/v1/modules/entitlements", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          active_modules: ["trading", "retail", "voice", "automations", "data"],
        }),
      });
    });

    await page.route("**/api/v1/billing/ai-credits", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          remaining: 4850,
          limit: 5000,
          used: 150,
        }),
      });
    });

    await page.route("**/api/v1/onboarding/branding", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          primary_color: "#0076FF",
          secondary_color: "#0B132B",
          accent_color: "#00D4FF",
        }),
      });
    });

    await page.route("**/api/v1/datasets/sources*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/v1/trading/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          message: "Flux publics Binance et Coinbase connectés.",
          streams: {
            binance: { status: "connected", ping_ms: 18, last_update: "2026-11-17T05:15:00Z" },
            coinbase: { status: "connected", ping_ms: 24, last_update: "2026-11-17T05:15:00Z" },
          },
        }),
      });
    });

    await page.route("**/api/v1/trading/watchlist", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          symbols: ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XAU/USD", "EUR/USD"],
        }),
      });
    });

    await page.route("**/api/v1/trading/asset-classes", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          classes: [
            { id: "crypto", name: "Cryptomonnaies", count: 3 },
            { id: "commodities", name: "Matières premières", count: 1 },
            { id: "forex", name: "Devises (Forex)", count: 1 },
          ],
        }),
      });
    });

    await page.route("**/api/v1/trading/candles*", async (route) => {
      const candles = generateCandles();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          candles,
          source: "Binance Live Public Feed",
          freshness: "realtime",
          indicators: {
            sma_20: 85210.4,
            ema_12: 85940.1,
            ema_26: 84890.3,
            rsi_14: 63.2,
            macd: { line: 243.6, signal: 185.2, histogram: 58.4 },
            bollinger: { middle: 85210.4, upper: 87920.0, lower: 82500.8 },
          },
        }),
      });
    });

    await page.route("**/api/v1/trading/quotes*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          quotes: [
            { symbol: "BTCUSDT", price: 86421.50, change_percent: 2.84, high_24h: 87100.0, low_24h: 84200.0, volume: 18450.2, freshness: "realtime" },
            { symbol: "ETHUSDT", price: 3128.40, change_percent: 1.87, high_24h: 3180.0, low_24h: 3050.0, volume: 94200.0, freshness: "realtime" },
            { symbol: "SOLUSDT", price: 218.60, change_percent: 4.31, high_24h: 224.0, low_24h: 208.0, volume: 421000.0, freshness: "realtime" },
            { symbol: "XAU/USD", price: 2654.30, change_percent: 0.45, high_24h: 2665.0, low_24h: 2640.0, volume: 12500.0, freshness: "delayed" },
            { symbol: "EUR/USD", price: 1.0544, change_percent: -0.21, high_24h: 1.0580, low_24h: 1.0520, volume: 890000.0, freshness: "delayed" },
          ],
        }),
      });
    });

    await page.route("**/api/v1/trading/rankings*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rows: [
            { symbol: "SOLUSDT", change_percent: 4.31, price: 218.60, high: 224.0, low: 208.0, volume: 421000 },
            { symbol: "BTCUSDT", change_percent: 2.84, price: 86421.50, high: 87100.0, low: 84200.0, volume: 18450 },
            { symbol: "ETHUSDT", change_percent: 1.87, price: 3128.40, high: 3180.0, low: 3050.0, volume: 94200 },
          ],
        }),
      });
    });

    await page.route("**/api/v1/trading/ask", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          answer: "Le BTC/USDT évolue en dynamique haussière au-dessus de sa moyenne mobile EMA 50 (85 210 $). Le RSI 14 à 63.2 signale un momentum acheteur sans surachat immédiat. Le support technique immédiat est à 84 890 $ et la résistance testée se situe à 87 920 $.",
          study_return: 0.427,
          holding_return: 0.185,
          sharpe_ratio: 1.38,
          max_drawdown: -0.064,
          win_rate: 0.582,
        }),
      });
    });

    console.log("Navigating to http://localhost:3008/trading ...");
    await page.goto("http://localhost:3008/trading", { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(2500);

    const elements = await page.evaluate(() => {
      const allDivs = Array.from(document.querySelectorAll("div"));
      const chartContainers = allDivs.filter((d) => d.className.includes("tv-lightweight-charts") || d.querySelector("canvas"));
      return {
        totalCanvases: document.querySelectorAll("canvas").length,
        hasChartContainer: chartContainers.length > 0,
        bodyHeight: document.body.scrollHeight,
      };
    });
    console.log("PAGE STATS:", elements);

    // Capture Full Station
    const fullPath = resolve(ARTIFACTS_DIR, "trading_dashboard_2_full.png");
    await page.screenshot({ path: fullPath, fullPage: true });
    console.log("Saved full dashboard screenshot to:", fullPath);

    // Locate the Lightweight Chart canvas
    const canvas = page.locator("canvas").first();
    if (await canvas.isVisible()) {
      const box = await canvas.boundingBox();
      if (box) {
        console.log("Moving mouse over chart canvas at coordinates:", box.x + box.width * 0.6, box.y + box.height * 0.4);
        await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.4);
        await page.waitForTimeout(1000);
      }
    }

    const chartPath = resolve(ARTIFACTS_DIR, "trading_interactive_chart_hover.png");
    await page.screenshot({ path: chartPath });
    console.log("Saved interactive chart with hover screenshot to:", chartPath);

    // Mobile Viewport Capture
    await page.setViewportSize({ width: 414, height: 896 });
    await page.waitForTimeout(1000);
    const mobilePath = resolve(ARTIFACTS_DIR, "trading_dashboard_2_mobile.png");
    await page.screenshot({ path: mobilePath, fullPage: true });
    console.log("Saved mobile dashboard screenshot to:", mobilePath);

  } catch (err) {
    console.error("Error during capture:", err);
  } finally {
    await browser.close();
  }
}

main();
