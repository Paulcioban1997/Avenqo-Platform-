/* Generated automatically. Do not edit manually. */
import type { LocaleCode } from "./types";
import catalogs from "./voice-industry-catalogs.generated.json";

export interface LocalizedIndustry {
  name: string;
  desc: string;
  category: string;
  icon: string;
  suggestedCapabilities: string[];
}

export interface VoiceIndustryCatalog {
  categories: Record<string, string>;
  ui: {
    sectionTitle: string;
    sectionSubtitle: string;
    searchPlaceholder: string;
    expandButton: string;
    collapseButton: string;
    customIndustryPrompt: string;
    customIndustryPlaceholder: string;
    suggestionsTitle: string;
    suggestionsDisclaimer: string;
    crmRequired: string;
    crmActive: string;
    retailRequired: string;
    retailActive: string;
    generalQa: string;
    noIndustrySelected: string;
    primarySector: string;
    selectedCount: string;
  };
  industries: Record<string, LocalizedIndustry>;
}

export const VOICE_INDUSTRY_CATALOGS = catalogs as Record<LocaleCode, VoiceIndustryCatalog>;

export function getVoiceIndustryCatalog(locale: LocaleCode | string): VoiceIndustryCatalog {
  return (VOICE_INDUSTRY_CATALOGS as Record<string, VoiceIndustryCatalog>)[locale] ?? VOICE_INDUSTRY_CATALOGS.fr;
}

export function getLocalizedCategory(categoryId: string, locale: LocaleCode | string): string {
  const cat = getVoiceIndustryCatalog(locale);
  return cat.categories[categoryId] ?? categoryId;
}

export function getLocalizedIndustry(industryId: string, locale: LocaleCode | string): LocalizedIndustry | null {
  const cat = getVoiceIndustryCatalog(locale);
  return cat.industries[industryId] ?? null;
}

export function getVoiceIndustryUi(locale: LocaleCode | string) {
  return getVoiceIndustryCatalog(locale).ui;
}
