"""Tenant business data, never permission grants or provider credentials."""
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from backend.app.schemas.voice import VoiceConfigRequest
from backend.app.services.tenant_locale_service import assert_locale_in_catalog


class VoiceBusinessProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(default=0, ge=0)
    business_name: str = Field(min_length=1, max_length=255)
    industry: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=3000)
    activities: list[str] = Field(default_factory=list, max_length=20)
    locations: list[str] = Field(default_factory=list, max_length=25)
    timezone: str = Field(default="America/Toronto", max_length=80)
    opening_hours: dict = Field(default_factory=dict)
    primary_locale: str = "fr"
    secondary_locales: list[str] = Field(default_factory=list, max_length=43)
    # Display-only business contact, never the agent's telephony routing number.
    # Preserve formatted legacy company contacts rather than breaking onboarding.
    contact_phone: str | None = Field(default=None, max_length=32)
    website: str = Field(default="", max_length=255)
    bookable_service_ids: list[UUID] = Field(default_factory=list, max_length=100)
    allowed_actions: list[str] = Field(default_factory=list, max_length=100)
    cancellation_policy: str = Field(default="", max_length=1500)
    communication_style: str = Field(default="professional", max_length=120)
    accent_preference: str = Field(default="", max_length=120)
    vocabulary: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("activities", "locations", "vocabulary")
    @classmethod
    def bounded_items(cls, items):
        if any(not item.strip() or len(item) > 250 for item in items):
            raise ValueError("Entries must contain 1 to 250 characters")
        return list(dict.fromkeys(item.strip() for item in items))

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError("Unknown timezone") from None
        return value

    @field_validator("primary_locale")
    @classmethod
    def primary(cls, value):
        return assert_locale_in_catalog(value)

    @field_validator("secondary_locales")
    @classmethod
    def secondary(cls, values):
        return list(dict.fromkeys(assert_locale_in_catalog(value) for value in values))

    @field_validator("opening_hours")
    @classmethod
    def hours(cls, value):
        return VoiceConfigRequest.validate_opening_hours(value)

    @field_validator("website")
    @classmethod
    def website_url(cls, value):
        from urllib.parse import urlsplit
        if value:
            url = urlsplit(value)
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
                raise ValueError("Website must be a public HTTP(S) address without credentials")
        return value
