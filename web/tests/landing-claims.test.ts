import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { LOCALES } from "../src/lib/i18n/locales";
import { TRANSLATIONS } from "../src/lib/i18n/dictionary";

const forbiddenClaims = /essayer gratuitement|try for free|probar gratis|free[- ]trial|essai gratuit|no credit card|sans carte bancaire|14[- ]day|14 jours|14 días/i;

function readSource(path: string): string {
  return readFileSync(resolve(process.cwd(), "src", path), "utf8");
}

describe("public signup messaging", () => {
  it("uses direct signup wording for every supported locale", () => {
    expect(LOCALES).toHaveLength(44);
    for (const locale of LOCALES) {
      const catalog = TRANSLATIONS[locale.code] as { common: { tryFree: string } };
      expect(catalog.common.tryFree, locale.code).toBeTruthy();
      expect(catalog.common.tryFree, locale.code).not.toMatch(forbiddenClaims);
    }

    expect(TRANSLATIONS.en.common.tryFree).toBe("Get started");
    expect(TRANSLATIONS.fr.common.tryFree).toBe("Créer votre espace");
  });

  it("keeps public signup surfaces on the canonical route", () => {
    for (const path of ["components/header.tsx", "components/landing-page.tsx", "components/pricing-content.tsx"]) {
      const source = readSource(path);
      expect(source, path).not.toContain("/register");
    }
  });

  it("contains no unsupported trial or no-card claims in public catalogs", () => {
    expect(JSON.stringify(TRANSLATIONS)).not.toMatch(forbiddenClaims);
  });
});
