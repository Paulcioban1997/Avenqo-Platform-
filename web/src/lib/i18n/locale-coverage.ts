import { LOCALES } from "./locales";
import { CONTRACTS_UI_EXPLICIT, type ContractsUiCopy } from "./contracts-ui-copy";
import { WORKSPACE_CHROME_EXPLICIT, type WorkspaceChromeCopy } from "./workspace-chrome-copy";

export interface CatalogCoverage {
  name: string;
  keyCount: number;
  localeCount: number;
  explicitLocales: string[];
  missingLocales: string[];
  explicitKeySlots: number;
  missingKeySlots: number;
}

function coverage(name: string, explicit: Record<string, object>, sample: object): CatalogCoverage {
  const locales = LOCALES.map((locale) => locale.code);
  const explicitLocales = locales.filter((code) => explicit[code]);
  const missingLocales = locales.filter((code) => !explicit[code]);
  const keyCount = Object.keys(sample).length;
  return {
    name,
    keyCount,
    localeCount: locales.length,
    explicitLocales,
    missingLocales,
    explicitKeySlots: explicitLocales.length * keyCount,
    missingKeySlots: missingLocales.length * keyCount,
  };
}

export function localeKeyCoverage(): CatalogCoverage[] {
  return [
    coverage("contractsUi", CONTRACTS_UI_EXPLICIT, CONTRACTS_UI_EXPLICIT.fr as ContractsUiCopy),
    coverage("workspaceChrome", WORKSPACE_CHROME_EXPLICIT, WORKSPACE_CHROME_EXPLICIT.fr as WorkspaceChromeCopy),
  ];
}
