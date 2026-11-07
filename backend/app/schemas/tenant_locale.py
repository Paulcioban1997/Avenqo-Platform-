"""HTTP contracts for the company-scoped linguistic profile."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.models.company_locale_profile import FALLBACK_POLICY_STAY_PRIMARY


class LocaleCapability(BaseModel):
    code: str
    audio_capability: str
    live_audio_validated: bool
    stt_available: bool
    tts_available: bool
    known_limitations: str | None = None


class TenantLocaleProfileResponse(BaseModel):
    company_id: UUID
    primary_locale: str | None
    secondary_locales: list[str]
    authorized_locales: list[str]
    voice_by_locale: dict[str, Any]
    fallback_policy: str
    fallback_policy_meaning: str
    suggested_locale: str | None
    suggested_secondaries: list[str]
    persisted: bool
    timezone: str
    timezone_source: str = "company.timezone"
    catalog_size: int = 44
    locales: list[LocaleCapability]
    note: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TenantLocaleProfileUpdate(BaseModel):
    primary_locale: str = Field(min_length=2, max_length=16)
    secondary_locales: list[str] = Field(default_factory=list, max_length=43)
    voice_by_locale: dict[str, Any] = Field(default_factory=dict)
    fallback_policy: str = Field(default=FALLBACK_POLICY_STAY_PRIMARY, max_length=32)

    @field_validator("primary_locale")
    @classmethod
    def strip_primary(cls, value: str) -> str:
        return value.strip()

    @field_validator("secondary_locales")
    @classmethod
    def normalize_secondaries(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item and item.strip()]

    @field_validator("fallback_policy")
    @classmethod
    def validate_fallback_policy(cls, value: str) -> str:
        normalized = (value or "").strip()
        if normalized != FALLBACK_POLICY_STAY_PRIMARY:
            raise ValueError("fallback_policy must be stay_primary (explain in primary, never silent EN)")
        return normalized

    @model_validator(mode="after")
    def secondaries_exclude_primary(self):
        self.secondary_locales = [code for code in self.secondary_locales if code != self.primary_locale]
        return self


class LocaleSuggestionResponse(BaseModel):
    country: str | None
    region: str | None
    timezone: str | None
    suggested_primary: str | None
    recommended_secondaries: list[str]
    applied: bool = False
    persisted: bool = False
    note: str
    locales: list[LocaleCapability] = Field(default_factory=list)
