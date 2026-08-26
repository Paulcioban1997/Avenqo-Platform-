"""Catalogue central localisation métier Avenqo — source de vérité UNIQUE.

Ce mapping fournit uniquement les DEFAULTS suggérés à la création
d'organisation (onboarding) : pays -> devise / timezone / langue suggérée.
Après création, la devise réellement utilisée est `Company.currency_code`
(jamais déduite de la langue).

NE JAMAIS utiliser ce catalogue pour convertir des montants (aucun FX inventé).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LocaleInfo:
    locale: str
    country_code: str  # ISO-3166-1 alpha-2
    country: str
    currency_code: str  # ISO-4217
    default_timezone: str


# 42 locales actuellement supportées par l'app.
LOCALES: tuple[LocaleInfo, ...] = (
    LocaleInfo("fr", "CA", "Canada", "CAD", "America/Toronto"),
    LocaleInfo("en", "US", "United States", "USD", "America/New_York"),
    LocaleInfo("es", "ES", "Spain", "EUR", "Europe/Madrid"),
    LocaleInfo("pt", "PT", "Portugal", "EUR", "Europe/Lisbon"),
    LocaleInfo("ro", "RO", "Romania", "RON", "Europe/Bucharest"),
    LocaleInfo("de", "DE", "Germany", "EUR", "Europe/Berlin"),
    LocaleInfo("it", "IT", "Italy", "EUR", "Europe/Rome"),
    LocaleInfo("nl", "NL", "Netherlands", "EUR", "Europe/Amsterdam"),
    LocaleInfo("pl", "PL", "Poland", "PLN", "Europe/Warsaw"),
    LocaleInfo("ru", "RU", "Russia", "RUB", "Europe/Moscow"),
    LocaleInfo("uk", "UA", "Ukraine", "UAH", "Europe/Kyiv"),
    LocaleInfo("el", "GR", "Greece", "EUR", "Europe/Athens"),
    LocaleInfo("sv", "SE", "Sweden", "SEK", "Europe/Stockholm"),
    LocaleInfo("tr", "TR", "Turkey", "TRY", "Europe/Istanbul"),
    LocaleInfo("cs", "CZ", "Czechia", "CZK", "Europe/Prague"),
    LocaleInfo("ka", "GE", "Georgia", "GEL", "Asia/Tbilisi"),
    LocaleInfo("hy", "AM", "Armenia", "AMD", "Asia/Yerevan"),
    LocaleInfo("ar", "SA", "Saudi Arabia", "SAR", "Asia/Riyadh"),
    LocaleInfo("ar-EG", "EG", "Egypt", "EGP", "Africa/Cairo"),
    LocaleInfo("he", "IL", "Israel", "ILS", "Asia/Jerusalem"),
    LocaleInfo("fa", "IR", "Iran", "IRR", "Asia/Tehran"),
    LocaleInfo("sw", "KE", "Kenya", "KES", "Africa/Nairobi"),
    LocaleInfo("am", "ET", "Ethiopia", "ETB", "Africa/Addis_Ababa"),
    LocaleInfo("af", "ZA", "South Africa", "ZAR", "Africa/Johannesburg"),
    LocaleInfo("ha", "NG", "Nigeria", "NGN", "Africa/Lagos"),
    LocaleInfo("zh", "CN", "China", "CNY", "Asia/Shanghai"),
    LocaleInfo("ja", "JP", "Japan", "JPY", "Asia/Tokyo"),
    LocaleInfo("ko", "KR", "South Korea", "KRW", "Asia/Seoul"),
    LocaleInfo("hi", "IN", "India", "INR", "Asia/Kolkata"),
    LocaleInfo("bn", "BD", "Bangladesh", "BDT", "Asia/Dhaka"),
    LocaleInfo("ur", "PK", "Pakistan", "PKR", "Asia/Karachi"),
    LocaleInfo("ta", "IN", "India", "INR", "Asia/Kolkata"),
    LocaleInfo("pa", "IN", "India", "INR", "Asia/Kolkata"),
    LocaleInfo("ne", "NP", "Nepal", "NPR", "Asia/Kathmandu"),
    LocaleInfo("vi", "VN", "Vietnam", "VND", "Asia/Ho_Chi_Minh"),
    LocaleInfo("th", "TH", "Thailand", "THB", "Asia/Bangkok"),
    LocaleInfo("id", "ID", "Indonesia", "IDR", "Asia/Jakarta"),
    LocaleInfo("ms", "MY", "Malaysia", "MYR", "Asia/Kuala_Lumpur"),
    LocaleInfo("tl", "PH", "Philippines", "PHP", "Asia/Manila"),
    LocaleInfo("my", "MM", "Myanmar", "MMK", "Asia/Yangon"),
    LocaleInfo("km", "KH", "Cambodia", "KHR", "Asia/Phnom_Penh"),
    LocaleInfo("mn", "MN", "Mongolia", "MNT", "Asia/Ulaanbaatar"),
)

BY_COUNTRY: dict[str, LocaleInfo] = {}
for _info in LOCALES:
    BY_COUNTRY.setdefault(_info.country.lower(), _info)
    BY_COUNTRY.setdefault(_info.country_code.lower(), _info)

BY_LOCALE: dict[str, LocaleInfo] = {info.locale: info for info in LOCALES}

# Fallback technique uniquement quand le pays n'est pas reconnu (jamais un
# choix métier déduit de la langue).
FALLBACK_CURRENCY = "USD"


def defaults_for_country(country: str) -> LocaleInfo | None:
    """Defaults (devise/timezone/langue suggérée) pour un pays d'onboarding."""

    return BY_COUNTRY.get((country or "").strip().lower())


def currency_for_country(country: str) -> str:
    info = defaults_for_country(country)
    return info.currency_code if info is not None else FALLBACK_CURRENCY


def distinct_currencies() -> frozenset[str]:
    return frozenset(info.currency_code for info in LOCALES)
