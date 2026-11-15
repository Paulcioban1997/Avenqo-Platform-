import { getApplicationCatalog } from "./generated-app-catalogs";
import type { LocaleCode } from "./types";

export type WorkspaceChromeCopy = {
  modules: string;
  contracts: string;
  security: string;
  legal: string;
  modulesOutOfSync: string;
  retry: string;
  whiteLabel: string;
  userFallback: string;
  memberFallback: string;
};

const fr: WorkspaceChromeCopy = {
  modules: "Modules",
  contracts: "Contrats",
  security: "Sécurité et confiance",
  legal: "Juridique",
  modulesOutOfSync: "Modules non synchronisés",
  retry: "Réessayer",
  whiteLabel: "Espace marque blanche",
  userFallback: "Utilisateur",
  memberFallback: "Membre",
};

const en: WorkspaceChromeCopy = {
  modules: "Modules",
  contracts: "Contracts",
  security: "Security and trust",
  legal: "Legal",
  modulesOutOfSync: "Modules out of sync",
  retry: "Retry",
  whiteLabel: "White-label workspace",
  userFallback: "User",
  memberFallback: "Member",
};

export const WORKSPACE_CHROME_EXPLICIT: Partial<Record<LocaleCode, WorkspaceChromeCopy>> = {
  fr,
  "fr-FR": fr,
  en,
  "en-GB": en,
};

/** Existing assistant catalog. Not a new translation. */
export const WORKSPACE_CATALOG_BACKED_KEYS = ["retry"] as const;

export function getWorkspaceChrome(locale: string): {
  copy: WorkspaceChromeCopy;
  explicit: boolean;
  catalogBackedKeys: readonly string[];
} {
  const direct = WORKSPACE_CHROME_EXPLICIT[locale as LocaleCode];
  const fallback = locale.toLowerCase().startsWith("fr") ? "fr" : "en";
  const base = direct ?? (WORKSPACE_CHROME_EXPLICIT[fallback] as WorkspaceChromeCopy);
  return {
    copy: { ...base, retry: getApplicationCatalog(locale).assistant.retry },
    explicit: Boolean(direct),
    catalogBackedKeys: WORKSPACE_CATALOG_BACKED_KEYS,
  };
}
