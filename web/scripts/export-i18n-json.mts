import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { LOCALES } from "../src/lib/i18n/locales";

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = join(__dirname, "../../frontend/assets/i18n");
mkdirSync(outDir, { recursive: true });

const manifest: string[] = [];

for (const locale of LOCALES) {
  // ar-EG.ts re-exports ar.ts via an extension-less specifier that Node's ESM
  // resolver can't follow directly; ar is already exported, so just reuse it here.
  const sourceCode = locale.code === "ar-EG" ? "ar" : locale.code;
  const mod = await import(`../src/lib/i18n/translations/${sourceCode}`);
  const translations = mod.default;
  writeFileSync(join(outDir, `${locale.code}.json`), JSON.stringify(translations, null, 2), "utf-8");
  manifest.push(locale.code);
  console.log("wrote", locale.code);
}

writeFileSync(
  join(outDir, "_locales.json"),
  JSON.stringify(
    LOCALES.map((l) => ({
      code: l.code,
      region: l.region,
      flag: l.flag,
      nativeName: l.nativeName,
      englishName: l.englishName,
      direction: l.direction,
    })),
    null,
    2,
  ),
  "utf-8",
);

console.log(`Done. ${manifest.length} locales exported to ${outDir}`);
