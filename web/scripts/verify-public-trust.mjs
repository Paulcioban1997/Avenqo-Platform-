import { createRequire } from "node:module";
import { mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const baseUrl = process.argv[2] || "http://localhost:3110";
const output = join(tmpdir(), "avenqo-trust-screenshots");
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const results = [];

try {
  for (const locale of ["en", "fr", "ar"]) {
    for (const [size, width, height] of [["desktop", 1440, 1000], ["tablet", 768, 1024], ["mobile", 390, 844]]) {
      for (const theme of ["light", "dark"]) {
        const context = await browser.newContext({ viewport: { width, height }, reducedMotion: "reduce", colorScheme: theme });
        const page = await context.newPage();
        const errors = [];
        page.on("pageerror", (error) => errors.push(error.message));
        await page.addInitScript(({ theme }) => localStorage.setItem("theme", theme), { theme });
        for (const route of ["/", "/trust", "/privacy"]) {
          const response = await page.goto(`${baseUrl}${route}?lang=${locale}`, { waitUntil: "networkidle" });
          await page.waitForFunction((locale) => document.documentElement.lang === locale, locale);
          await page.evaluate((theme) => document.documentElement.classList.toggle("dark", theme === "dark"), theme);
          const animated = await page.locator(".trust-card, .research-note").all();
          for (const element of animated) {
            await element.scrollIntoViewIfNeeded();
            await element.evaluate((node) => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
          }
          const geometry = await page.evaluate(() => {
            const nodes = [...document.querySelectorAll(".trust-card, .research-note, .privacy-sections article")];
            return {
              dir: document.documentElement.dir,
              newContentOverflow: nodes.some((node) => node.scrollWidth > node.clientWidth + 2),
              clippedText: nodes.some((node) => [...node.querySelectorAll("h2, h3, p")].some((text) => text.scrollHeight > text.clientHeight + 2 || text.scrollWidth > text.clientWidth + 2)),
              outsideViewport: nodes.some((node) => {
                const rect = node.getBoundingClientRect();
                return rect.left < -2 || rect.right > innerWidth + 2;
              }),
              trustCards: document.querySelectorAll(".trust-grid article").length,
              principles: document.querySelectorAll(".principle-grid article").length,
              privacyTopics: document.querySelectorAll(".privacy-shell .privacy-sections article").length,
            };
          });
          const links = await page.locator('a[href="https://lawzero.org/"]').count();
          const passed = response?.status() === 200 && errors.length === 0
            && geometry.dir === (locale === "ar" ? "rtl" : "ltr")
            && !geometry.newContentOverflow && !geometry.clippedText && !geometry.outsideViewport
            && (route === "/privacy" ? geometry.privacyTopics === 7 : geometry.trustCards === 6 && geometry.principles === 4 && links === 1);
          results.push({ route, locale, size, theme, passed, ...geometry, errors: [...errors] });
          if (route === "/" && size !== "tablet") {
            const screenshotStyle = ".site-header { visibility: hidden !important; }";
            await page.locator(".trust-section").screenshot({ path: join(output, `${locale}-${size}-${theme}-trust.png`), style: screenshotStyle });
            await page.locator(".research-note").screenshot({ path: join(output, `${locale}-${size}-${theme}-research.png`), style: screenshotStyle });
          }
        }
        await context.close();
      }
    }
  }
  const failures = results.filter((result) => !result.passed);
  console.log(JSON.stringify({ baseUrl, checks: results.length, passed: results.length - failures.length, failures, screenshots: output }, null, 2));
  if (failures.length) process.exitCode = 1;
} finally {
  await browser.close();
}