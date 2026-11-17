import { LOCALES } from "./locales";
import { CONTRACTS_CATALOG_BACKED_KEYS, CONTRACTS_UI_EXPLICIT, type ContractsUiCopy } from "./contracts-ui-copy";
import { SOURCE_SELECTOR_COPY } from "./source-selector-copy";
import { WORKSPACE_CATALOG_BACKED_KEYS, WORKSPACE_CHROME_EXPLICIT, type WorkspaceChromeCopy } from "./workspace-chrome-copy";

export interface CatalogCoverage {
  name: string;
  keyCount: number;
  localeCount: number;
  explicitLocales: string[];
  missingLocales: string[];
  catalogBackedKeys: string[];
  fallbackKeyCount: number;
  catalogBackedSlots: number;
  explicitKeySlots: number;
  missingKeySlots: number;
}

function coverage(
  name: string,
  explicit: Record<string, object>,
  sample: object,
  catalogBackedKeys: readonly string[],
): CatalogCoverage {
  const locales = LOCALES.map((locale) => locale.code);
  const explicitLocales = locales.filter((code) => explicit[code]);
  const missingLocales = locales.filter((code) => !explicit[code]);
  const keyCount = Object.keys(sample).length;
  const fallbackKeyCount = keyCount - catalogBackedKeys.length;
  return {
    name,
    keyCount,
    localeCount: locales.length,
    explicitLocales,
    missingLocales,
    catalogBackedKeys: [...catalogBackedKeys],
    fallbackKeyCount,
    catalogBackedSlots: locales.length * catalogBackedKeys.length,
    explicitKeySlots: explicitLocales.length * fallbackKeyCount,
    missingKeySlots: missingLocales.length * fallbackKeyCount,
  };
}

export function localeKeyCoverage(): CatalogCoverage[] {
  const locales = LOCALES.map((locale) => locale.code);
  const sourceLocales = locales.filter((code) => SOURCE_SELECTOR_COPY[code]?.every((value) => value.trim().length > 0));
  const sourceMissing = locales.filter((code) => !sourceLocales.includes(code));
  return [
    coverage("contractsUi", CONTRACTS_UI_EXPLICIT, CONTRACTS_UI_EXPLICIT.fr as ContractsUiCopy, CONTRACTS_CATALOG_BACKED_KEYS),
    coverage("workspaceChrome", WORKSPACE_CHROME_EXPLICIT, WORKSPACE_CHROME_EXPLICIT.fr as WorkspaceChromeCopy, WORKSPACE_CATALOG_BACKED_KEYS),
    {
      name: "sourceSelector",
      keyCount: 2,
      localeCount: locales.length,
      explicitLocales: sourceLocales,
      missingLocales: sourceMissing,
      catalogBackedKeys: ["label", "allActive"],
      fallbackKeyCount: 0,
      catalogBackedSlots: sourceLocales.length * 2,
      explicitKeySlots: 0,
      missingKeySlots: sourceMissing.length * 2,
    },
  ];
}
