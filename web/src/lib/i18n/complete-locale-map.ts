import type { LocaleCode } from "./types";
import { LOCALES } from "./locales";

/** Fill every canonical locale, using exact → language prefix → French family → English. */
export function completeLocaleMap<T extends Record<string, string>>(
  variants: Partial<Record<LocaleCode, T>> & { en: T; fr: T },
): Record<LocaleCode, T> {
  const filled = {} as Record<LocaleCode, T>;
  for (const locale of LOCALES) {
    const language = locale.code.split("-")[0] as LocaleCode;
    filled[locale.code] =
      variants[locale.code] ??
      variants[language] ??
      (locale.code.startsWith("fr") ? variants.fr : variants.en);
  }
  return filled;
}
