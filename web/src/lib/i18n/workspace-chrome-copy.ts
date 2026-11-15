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

export function getWorkspaceChrome(locale: string): { copy: WorkspaceChromeCopy; explicit: boolean } {
  const direct = WORKSPACE_CHROME_EXPLICIT[locale as LocaleCode];
  if (direct) return { copy: direct, explicit: true };
  const fallback = locale.toLowerCase().startsWith("fr") ? "fr" : "en";
  return { copy: WORKSPACE_CHROME_EXPLICIT[fallback] as WorkspaceChromeCopy, explicit: false };
}
