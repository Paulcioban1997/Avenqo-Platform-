import type { LocaleCode, Translations } from "./types";
import { DEFAULT_LOCALE } from "./locales";
import ar from "./translations/ar";
import arEG from "./translations/ar-EG";
import en from "./translations/en";
import es from "./translations/es";
import fr from "./translations/fr";
import ja from "./translations/ja";
import ko from "./translations/ko";
import pt from "./translations/pt";
import ro from "./translations/ro";
import zh from "./translations/zh";
import de from "./translations/de";
import it from "./translations/it";
import nl from "./translations/nl";
import pl from "./translations/pl";
import ru from "./translations/ru";
import uk from "./translations/uk";
import el from "./translations/el";
import sv from "./translations/sv";
import tr from "./translations/tr";
import cs from "./translations/cs";
import ka from "./translations/ka";
import hy from "./translations/hy";
import he from "./translations/he";
import fa from "./translations/fa";
import sw from "./translations/sw";
import am from "./translations/am";
import af from "./translations/af";
import ha from "./translations/ha";
import hi from "./translations/hi";
import bn from "./translations/bn";
import ur from "./translations/ur";
import ta from "./translations/ta";
import pa from "./translations/pa";
import ne from "./translations/ne";
import vi from "./translations/vi";
import th from "./translations/th";
import id from "./translations/id";
import ms from "./translations/ms";
import tl from "./translations/tl";
import my from "./translations/my";
import km from "./translations/km";
import mn from "./translations/mn";

/** Source de vérité unique associant chaque locale à ses traductions complètes. */
export const TRANSLATIONS: Record<LocaleCode, Translations> = {
  fr,
  en,
  es,
  pt,
  ro,
  ar,
  "ar-EG": arEG,
  zh,
  ja,
  ko,
  de,
  it,
  nl,
  pl,
  ru,
  uk,
  el,
  sv,
  tr,
  cs,
  he,
  fa,
  sw,
  am,
  af,
  ha,
  hi,
  bn,
  ur,
  ta,
  pa,
  ne,
  vi,
  th,
  id,
  ms,
  tl,
  my,
  km,
  mn,
  ka,
  hy,
};

/** Retourne les traductions d'une locale, avec repli sur la locale par défaut si absente. */
export function getTranslations(locale: LocaleCode): Translations {
  return TRANSLATIONS[locale] ?? TRANSLATIONS[DEFAULT_LOCALE];
}
