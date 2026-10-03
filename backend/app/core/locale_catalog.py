"""Canonical Avenqo locale contract and deterministic BCP-47 resolution."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata


@dataclass(frozen=True, slots=True)
class LocaleInfo:
    locale: str
    bcp47: str
    region: str
    flag: str
    native_name: str
    english_name: str
    direction: str
    fallback: str
    country_code: str
    country: str
    currency_code: str
    default_timezone: str


@dataclass(frozen=True, slots=True)
class LanguageDetection:
    locale: str | None
    language_code: str | None
    confidence: float | None
    source: str


_SOURCE = Path(__file__).resolve().parents[3] / "shared" / "locales" / "canonical_locales.json"
_RAW_LOCALES = json.loads(_SOURCE.read_text(encoding="utf-8"))
_COUNTRY_NAMES = {
    "CA": "Canada", "US": "United States", "ES": "Spain", "BR": "Brazil",
    "FR": "France", "GB": "United Kingdom", "RO": "Romania", "DE": "Germany",
    "IT": "Italy", "NL": "Netherlands", "PL": "Poland", "RU": "Russia",
    "UA": "Ukraine", "GR": "Greece", "SE": "Sweden", "TR": "Turkey",
    "CZ": "Czechia", "GE": "Georgia", "AM": "Armenia", "SA": "Saudi Arabia",
    "EG": "Egypt", "IL": "Israel", "IR": "Iran", "KE": "Kenya",
    "ET": "Ethiopia", "ZA": "South Africa", "NG": "Nigeria", "CN": "China",
    "JP": "Japan", "KR": "South Korea", "IN": "India", "BD": "Bangladesh",
    "PK": "Pakistan", "LK": "Sri Lanka", "NP": "Nepal", "VN": "Vietnam",
    "TH": "Thailand", "ID": "Indonesia", "MY": "Malaysia", "PH": "Philippines",
    "MM": "Myanmar", "KH": "Cambodia", "MN": "Mongolia",
}
LOCALES: tuple[LocaleInfo, ...] = tuple(
    LocaleInfo(
        locale=item["code"],
        bcp47=item["bcp47"],
        region=item["region"],
        flag=item["flag"],
        native_name=item["nativeName"],
        english_name=item["englishName"],
        direction=item["direction"],
        fallback=item["fallback"],
        country_code=item["bcp47"].split("-")[-1].upper(),
        country=_COUNTRY_NAMES[item["bcp47"].split("-")[-1].upper()],
        currency_code=item["currency"],
        default_timezone=item["timezone"],
    )
    for item in _RAW_LOCALES
)

if len(LOCALES) != 44 or len({item.locale for item in LOCALES}) != 44:
    raise RuntimeError("Avenqo canonical locale contract must contain exactly 44 unique locales")

BY_LOCALE = {item.locale.casefold(): item for item in LOCALES}
BY_BCP47 = {item.bcp47.casefold(): item for item in LOCALES}
FALLBACK_CURRENCY = "USD"
DEFAULT_LOCALE = "fr"

_ALIASES = {
    "fr-ca": "fr",
    "en-us": "en",
    "es-es": "es",
    "es-419": "es",
    "es-latam": "es",
    "pt-pt": "pt",
    "pt-br": "pt",
}


def resolve_locale(raw_locale: str | None, *, fallback: str = DEFAULT_LOCALE) -> str:
    """Resolve explicit BCP-47/underscore aliases to one canonical locale."""

    normalized = (raw_locale or "").strip().replace("_", "-").casefold()
    if normalized in _ALIASES:
        return _ALIASES[normalized]
    exact = BY_LOCALE.get(normalized) or BY_BCP47.get(normalized)
    if exact is not None:
        return exact.locale
    language = normalized.split("-", 1)[0]
    for info in LOCALES:
        if info.locale.casefold() == language or info.bcp47.split("-", 1)[0].casefold() == language:
            return info.locale
    if fallback.casefold() != normalized:
        return resolve_locale(fallback)
    return DEFAULT_LOCALE


def locale_info(raw_locale: str | None) -> LocaleInfo:
    return BY_LOCALE[resolve_locale(raw_locale).casefold()]


_LANGUAGE_SWITCHES = (
    ("es", ("en español", "en espanol", "responde en español")),
    ("en", ("in english", "answer in english", "réponds en anglais")),
    ("fr", ("en français", "en francais", "réponds en français")),
    ("de", ("auf deutsch", "auf deutsch antworten")),
    ("it", ("in italiano", "rispondi in italiano")),
    ("pt", ("em português", "em portugues")),
    ("ro", ("în română", "in romana")),
)
_HAUSA_MARKERS = frozenset({
    "yaya", "kake", "kike", "nake", "muke", "suke", "sannu", "lafiya",
    "yanzu", "wannan", "menene", "taimako", "akwai", "yadda", "sayi",
    "kaya", "odarka", "rubuta", "magana",
})


@lru_cache(maxsize=1)
def _language_identifier():
    from langid.langid import LanguageIdentifier, model

    identifier = LanguageIdentifier.from_modelstring(model, norm_probs=True)
    canonical_codes = {
        item.bcp47.split("-", 1)[0].casefold()
        for item in LOCALES
    }
    supported_codes = canonical_codes.intersection(identifier.nb_classes)
    identifier.set_languages(sorted(supported_codes))
    return identifier, frozenset(supported_codes)


def _fold_language_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^\w]+", " ", without_marks, flags=re.UNICODE).strip()


def _locale_for_language_code(language_code: str, preferred_locale: str | None = None) -> str | None:
    normalized_code = language_code.casefold()
    matches = tuple(
        item for item in LOCALES
        if item.locale.casefold() == normalized_code
        or item.bcp47.split("-", 1)[0].casefold() == normalized_code
    )
    if not matches:
        return None
    if preferred_locale:
        preferred = resolve_locale(preferred_locale)
        if any(item.locale == preferred for item in matches):
            return preferred
    return next((item.locale for item in matches if item.locale.casefold() == normalized_code), matches[0].locale)


def _explicit_language_override(text: str, preferred_locale: str | None) -> str | None:
    folded = _fold_language_text(text)
    connectors = r"(?:in|en|em|auf|a|à|på|na|no|em|in|به زبان)"
    commands = r"(?:answer|respond|reply|speak|continue|switch|change|use|responde|respondeme|reponde|raspunde|vorbeste|habla|contesta|cambia|parla|rispondi|sprechen)"
    aliases: dict[str, set[str]] = {}
    for info in LOCALES:
        locale_aliases = {
            info.native_name,
            info.english_name,
            info.native_name.split("(", 1)[0].strip(),
            info.english_name.split("(", 1)[0].strip(),
            info.locale,
            info.bcp47,
        }
        for alias in locale_aliases:
            folded_alias = _fold_language_text(alias)
            if len(folded_alias) < 3 and alias not in {info.locale, info.bcp47}:
                continue
            escaped = re.escape(folded_alias).replace(r"\ ", r"\s+")
            aliases.setdefault(escaped, set()).add(info.locale)

    for escaped in sorted(aliases, key=len, reverse=True):
        alias_pattern = rf"\b{escaped}(?![\w-])"
        if re.search(rf"\b{connectors}\s+{alias_pattern}", folded):
            matching_locales = aliases[escaped]
            preferred = resolve_locale(preferred_locale) if preferred_locale else None
            if preferred in matching_locales:
                return preferred
            return next(info.locale for info in LOCALES if info.locale in matching_locales)
        if re.search(rf"\b{commands}\b.{{0,50}}{alias_pattern}", folded):
            matching_locales = aliases[escaped]
            preferred = resolve_locale(preferred_locale) if preferred_locale else None
            if preferred in matching_locales:
                return preferred
            return next(info.locale for info in LOCALES if info.locale in matching_locales)

    for language_code, markers in _LANGUAGE_SWITCHES:
        if any(_fold_language_text(marker) in folded for marker in markers):
            return _locale_for_language_code(language_code, preferred_locale)
    return None


def detect_spoken_language(text: str, *, preferred_locale: str | None = None) -> LanguageDetection:
    """Detect each utterance locally; return unknown rather than guessing a fallback locale."""

    normalized = (text or "").casefold().strip()
    if not normalized:
        return LanguageDetection(None, None, None, "empty")

    explicit_locale = _explicit_language_override(normalized, preferred_locale)
    if explicit_locale is not None:
        return LanguageDetection(explicit_locale, explicit_locale.split("-", 1)[0], 1.0, "explicit_request")

    if any("\u1000" <= char <= "\u109f" or "\ua9e0" <= char <= "\ua9ff" for char in normalized):
        return LanguageDetection(_locale_for_language_code("my", preferred_locale), "my", 1.0, "script")
    words = set(_fold_language_text(normalized).split())
    if len(words.intersection(_HAUSA_MARKERS)) >= 2 or any(char in normalized for char in "ɓɗƙƴƁƊƘƳ"):
        return LanguageDetection(_locale_for_language_code("ha", preferred_locale), "ha", 0.95, "lexical")
    if any("\u3040" <= char <= "\u30ff" for char in normalized):
        return LanguageDetection(_locale_for_language_code("ja", preferred_locale), "ja", 1.0, "script")
    if any("\u4e00" <= char <= "\u9fff" for char in normalized):
        return LanguageDetection(_locale_for_language_code("zh", preferred_locale), "zh", 1.0, "script")
    if any("\uac00" <= char <= "\ud7af" for char in normalized):
        return LanguageDetection(_locale_for_language_code("ko", preferred_locale), "ko", 1.0, "script")
    if sum(char.isalpha() for char in normalized) < 5:
        return LanguageDetection(None, None, None, "insufficient_text")

    identifier, supported_codes = _language_identifier()
    language_code, confidence = identifier.classify(normalized)
    confidence = float(confidence)
    if language_code not in supported_codes or confidence < 0.80:
        return LanguageDetection(None, None, confidence, "undetermined")
    locale = _locale_for_language_code(language_code, preferred_locale)
    if locale is None:
        return LanguageDetection(None, language_code, confidence, "unsupported")
    return LanguageDetection(locale, language_code, confidence, "detector")


def voice_language_detection_support() -> dict[str, str]:
    """Per-canonical-locale detector path, derived from the single locale registry."""

    _, supported_codes = _language_identifier()
    return {
        item.locale: (
            "script" if item.bcp47.split("-", 1)[0].casefold() == "my"
            else "lexical" if item.bcp47.split("-", 1)[0].casefold() == "ha"
            else "detector" if item.bcp47.split("-", 1)[0].casefold() in supported_codes
            else "fallback_required"
        )
        for item in LOCALES
    }


def detect_locale_from_text(text: str) -> str | None:
    """Compatibility wrapper returning only a confidently detected canonical locale."""

    return detect_spoken_language(text).locale


def defaults_for_country(country: str) -> LocaleInfo | None:
    normalized = (country or "").strip().casefold()
    for info in LOCALES:
        if info.country_code.casefold() == normalized or info.country.casefold() == normalized:
            return info
    return None


def currency_for_country(country: str) -> str:
    info = defaults_for_country(country)
    return info.currency_code if info is not None else FALLBACK_CURRENCY


def distinct_currencies() -> frozenset[str]:
    return frozenset(info.currency_code for info in LOCALES)
