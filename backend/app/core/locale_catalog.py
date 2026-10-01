"""Canonical Avenqo locale contract and deterministic BCP-47 resolution."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


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
