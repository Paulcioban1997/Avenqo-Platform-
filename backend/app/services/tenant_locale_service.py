"""Shared company-scoped linguistic profile reader for every Avenqo module.

Any module (Voice, CRM, Retail, billing/notifications, Central AI, auth,
onboarding, employees, public booking) can resolve the tenant locale with:

    from backend.app.services.tenant_locale_service import get_company_locale, get_profile

Rules:
- Official catalog only (exactly 44 codes in shared/locales/canonical_locales.json).
- Country / region / timezone are SUGGESTIONS. They never persist and never
  override an explicit primary_locale.
- secondary_locales default empty. en/fr are never auto-added.
- Timezone for dates stays on Company.timezone — this service only exposes it.
- Audio capability is honest (SUPPORTED / PARTIAL / UNTESTED). UI 44 ≠ phone 44.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.locale_catalog import BY_BCP47, BY_LOCALE, LOCALES, defaults_for_country
from backend.app.models.company import Company
from backend.app.models.company_locale_profile import (
    FALLBACK_POLICY_STAY_PRIMARY,
    CompanyLocaleProfile,
)
from backend.app.voice.language_resolver import REGION_LANGUAGE_DATA, RegionLanguageResolver
from backend.app.voice.languages import get_voice_language_capability

CATALOG_SIZE = 44
FALLBACK_POLICY_MEANING = (
    "stay_primary: keep explaining in the company primary locale; "
    "never silently switch to English."
)
PROFILE_NOTE = (
    "UI catalog has 44 locales. That is not a telephony guarantee. "
    "Modules must use Company.timezone for dates. "
    "Country/region/timezone suggestions are never imposed."
)
AUDIO_SUPPORTED = "SUPPORTED"
AUDIO_PARTIAL = "PARTIAL"
AUDIO_UNSUPPORTED = "UNSUPPORTED"
AUDIO_UNTESTED = "UNTESTED"


class LocaleNotInCatalog(ValueError):
    """Raised when a locale is not one of the 44 official catalog codes."""


class TenantLocaleIsolationError(LookupError):
    """Raised when the requested company profile cannot be resolved for this tenant."""


@dataclass(frozen=True, slots=True)
class LocaleCapabilityView:
    code: str
    audio_capability: str
    live_audio_validated: bool
    stt_available: bool
    tts_available: bool
    known_limitations: str | None = None


@dataclass(frozen=True, slots=True)
class TenantLocaleProfileView:
    company_id: UUID
    primary_locale: str | None
    secondary_locales: list[str]
    authorized_locales: list[str]
    voice_by_locale: dict[str, Any]
    fallback_policy: str
    suggested_locale: str | None
    suggested_secondaries: list[str]
    persisted: bool
    timezone: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    locales: list[LocaleCapabilityView] = field(default_factory=list)

    @property
    def fallback_policy_meaning(self) -> str:
        return FALLBACK_POLICY_MEANING


def catalog_codes() -> frozenset[str]:
    return frozenset(item.locale for item in LOCALES)


def catalog_code_or_none(raw: str | None) -> str | None:
    """Map an alias/BCP-47 tag onto an official catalog code, or return None.

    Does not fall back to French or English. Unknown codes stay unknown.
    """

    if raw is None:
        return None
    normalized = raw.strip().replace("_", "-").casefold()
    if not normalized:
        return None
    exact = BY_LOCALE.get(normalized) or BY_BCP47.get(normalized)
    if exact is not None:
        return exact.locale
    from backend.app.core.locale_catalog import _ALIASES

    aliased = _ALIASES.get(normalized)
    if aliased is not None and aliased.casefold() in BY_LOCALE:
        return BY_LOCALE[aliased.casefold()].locale
    language = normalized.split("-", 1)[0]
    if language in BY_LOCALE:
        return BY_LOCALE[language].locale
    return None


def assert_locale_in_catalog(raw: str | None) -> str:
    code = catalog_code_or_none(raw)
    if code is None:
        raise LocaleNotInCatalog(f"Locale {raw!r} is not in the official 44-locale catalog")
    return code


def honest_audio_capability(locale: str) -> LocaleCapabilityView:
    """Expose telephony evidence without inventing FULLY_SUPPORTED."""

    code = assert_locale_in_catalog(locale)
    cap = get_voice_language_capability(code)
    if cap.get("locale") != code and cap.get("bcp47", "").casefold() != code.casefold():
        # get_voice_language_capability falls back to fr-CA for unknowns — never use that lie.
        return LocaleCapabilityView(
            code=code,
            audio_capability=AUDIO_UNTESTED,
            live_audio_validated=False,
            stt_available=False,
            tts_available=False,
            known_limitations="No capability row for this catalog locale.",
        )
    live = bool(cap.get("live_audio_validated"))
    stt = bool(cap.get("stt_available"))
    tts = bool(cap.get("tts_available"))
    if live:
        status = AUDIO_SUPPORTED
    elif stt or tts:
        status = AUDIO_PARTIAL
    else:
        status = AUDIO_UNTESTED
    return LocaleCapabilityView(
        code=code,
        audio_capability=status,
        live_audio_validated=live,
        stt_available=stt,
        tts_available=tts,
        known_limitations=str(cap.get("known_limitations") or "") or None,
    )


def capabilities_for(codes: list[str]) -> list[LocaleCapabilityView]:
    seen: list[str] = []
    for code in codes:
        if code not in seen:
            seen.append(code)
    return [honest_audio_capability(code) for code in seen]


def authorized_locales(profile: TenantLocaleProfileView | CompanyLocaleProfile) -> list[str]:
    primary = getattr(profile, "primary_locale", None)
    secondaries = list(getattr(profile, "secondary_locales", None) or [])
    ordered: list[str] = []
    if primary:
        ordered.append(primary)
    for code in secondaries:
        if code not in ordered:
            ordered.append(code)
    return ordered


def suggest_primary(
    country: str | None = None,
    region: str | None = None,
    timezone: str | None = None,
) -> tuple[str | None, list[str]]:
    """Suggestion only. Never persist. Never impose. Never auto-add en/fr."""

    suggested: str | None = None
    recommended: list[str] = []
    country_code = _country_code(country)

    if country_code and country_code in REGION_LANGUAGE_DATA:
        recommendation = RegionLanguageResolver.resolve(country_code, region=region)
        suggested = catalog_code_or_none(recommendation.primary_locale)
        for raw in recommendation.secondary_locales:
            mapped = catalog_code_or_none(raw)
            if mapped and mapped != suggested and mapped not in recommended:
                recommended.append(mapped)
    elif country:
        info = defaults_for_country(country) or defaults_for_country(country_code or "")
        if info is not None:
            suggested = info.locale

    if suggested is None and timezone:
        tz = timezone.strip()
        for info in LOCALES:
            if info.default_timezone == tz:
                suggested = info.locale
                break

    return suggested, recommended


def get_company(db: Session, company_id: UUID) -> Company | None:
    return db.scalar(select(Company).where(Company.id == company_id))


def get_stored_profile(db: Session, company_id: UUID) -> CompanyLocaleProfile | None:
    return db.scalar(
        select(CompanyLocaleProfile).where(CompanyLocaleProfile.company_id == company_id)
    )


def get_profile(db: Session, company_id: UUID) -> TenantLocaleProfileView:
    """Read the tenant profile. Does not persist suggestions."""

    company = get_company(db, company_id)
    if company is None:
        raise TenantLocaleIsolationError("company_not_found")
    stored = get_stored_profile(db, company_id)
    suggested, suggested_secondaries = suggest_primary(
        company.country, company.region, company.timezone
    )
    if stored is not None:
        primary = stored.primary_locale
        secondaries = [code for code in (stored.secondary_locales or []) if code != primary]
        view = TenantLocaleProfileView(
            company_id=company.id,
            primary_locale=primary,
            secondary_locales=secondaries,
            authorized_locales=[],
            voice_by_locale=dict(stored.voice_by_locale or {}),
            fallback_policy=stored.fallback_policy or FALLBACK_POLICY_STAY_PRIMARY,
            suggested_locale=suggested,
            suggested_secondaries=suggested_secondaries,
            persisted=True,
            timezone=company.timezone,
            created_at=stored.created_at,
            updated_at=stored.updated_at,
        )
    else:
        explicit = catalog_code_or_none(company.preferred_language)
        view = TenantLocaleProfileView(
            company_id=company.id,
            primary_locale=explicit,
            secondary_locales=[],
            authorized_locales=[],
            voice_by_locale={},
            fallback_policy=FALLBACK_POLICY_STAY_PRIMARY,
            suggested_locale=suggested,
            suggested_secondaries=suggested_secondaries,
            persisted=False,
            timezone=company.timezone,
        )
    locales = capabilities_for(authorized_locales(view) or ([suggested] if suggested else []))
    return TenantLocaleProfileView(
        company_id=view.company_id,
        primary_locale=view.primary_locale,
        secondary_locales=list(view.secondary_locales),
        authorized_locales=authorized_locales(view),
        voice_by_locale=dict(view.voice_by_locale),
        fallback_policy=view.fallback_policy,
        suggested_locale=view.suggested_locale,
        suggested_secondaries=list(view.suggested_secondaries),
        persisted=view.persisted,
        timezone=view.timezone,
        created_at=view.created_at,
        updated_at=view.updated_at,
        locales=locales,
    )


def get_company_locale(db: Session, company_id: UUID) -> str | None:
    """Thin hook: explicit profile primary, else catalog-valid Company.preferred_language.

    Never invent en/fr from country, phone, or IP. Returns None if the tenant
    has no catalog-valid explicit locale.
    """

    stored = get_stored_profile(db, company_id)
    if stored is not None:
        return stored.primary_locale
    company = get_company(db, company_id)
    if company is None:
        return None
    return catalog_code_or_none(company.preferred_language)


def normalize_secondary_locales(raw_secondaries: list[str] | None, primary: str) -> list[str]:
    """Persist only codes the company explicitly enabled and that are in the catalog."""

    ordered: list[str] = []
    for raw in raw_secondaries or []:
        code = assert_locale_in_catalog(raw)
        if code == primary or code in ordered:
            continue
        ordered.append(code)
    return ordered


def upsert_profile(
    db: Session,
    company_id: UUID,
    *,
    primary_locale: str,
    secondary_locales: list[str] | None = None,
    voice_by_locale: dict[str, Any] | None = None,
    fallback_policy: str = FALLBACK_POLICY_STAY_PRIMARY,
    sync_company_preferred_language: bool = True,
) -> TenantLocaleProfileView:
    company = get_company(db, company_id)
    if company is None:
        raise TenantLocaleIsolationError("company_not_found")
    primary = assert_locale_in_catalog(primary_locale)
    secondaries = normalize_secondary_locales(secondary_locales, primary)
    voices = _normalize_voice_by_locale(voice_by_locale)
    policy = fallback_policy.strip() if fallback_policy else FALLBACK_POLICY_STAY_PRIMARY
    if policy != FALLBACK_POLICY_STAY_PRIMARY:
        raise ValueError("fallback_policy must be stay_primary")

    stored = get_stored_profile(db, company_id)
    if stored is None:
        stored = CompanyLocaleProfile(
            company_id=company_id,
            primary_locale=primary,
            secondary_locales=secondaries,
            voice_by_locale=voices,
            fallback_policy=policy,
        )
        db.add(stored)
    else:
        stored.primary_locale = primary
        stored.secondary_locales = secondaries
        stored.voice_by_locale = voices
        stored.fallback_policy = policy
    if sync_company_preferred_language:
        company.preferred_language = primary
    db.flush()
    return get_profile(db, company_id)


def create_profile_for_new_company(db: Session, company: Company) -> CompanyLocaleProfile | None:
    """Create an empty-secondaries profile from the company's explicit signup locale."""

    primary = catalog_code_or_none(company.preferred_language)
    if primary is None or get_stored_profile(db, company.id) is not None:
        return None
    profile = CompanyLocaleProfile(
        company_id=company.id,
        primary_locale=primary,
        secondary_locales=[],
        voice_by_locale={},
        fallback_policy=FALLBACK_POLICY_STAY_PRIMARY,
    )
    db.add(profile)
    db.flush()
    return profile


def _normalize_voice_by_locale(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not raw:
        return {}
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        normalized[assert_locale_in_catalog(str(key))] = value
    return normalized


def _country_code(country: str | None) -> str | None:
    if not country:
        return None
    cleaned = country.strip()
    if len(cleaned) == 2:
        return cleaned.upper()
    from backend.app.core.locale_catalog import _COUNTRY_NAMES

    folded = cleaned.casefold()
    for code, name in _COUNTRY_NAMES.items():
        if name.casefold() == folded:
            return code
    aliases = {
        "canada": "CA",
        "united states": "US",
        "usa": "US",
        "france": "FR",
        "romania": "RO",
        "românia": "RO",
        "spain": "ES",
        "españa": "ES",
    }
    return aliases.get(folded)
