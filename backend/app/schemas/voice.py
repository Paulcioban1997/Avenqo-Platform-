"""HTTP contracts for tenant-configured voice agents and Retell tools."""

from __future__ import annotations

from datetime import date, datetime, time as datetime_time
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from backend.app.core.locale_catalog import BY_BCP47, BY_LOCALE, resolve_locale


class VoiceServiceConfig(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    duration_minutes: int = Field(ge=5, le=480)
    price: float = Field(default=0, ge=0)
    currency: str = Field(default="CAD", min_length=3, max_length=3)
    crm_service_id: UUID | None = None


class VoiceConfigRequest(BaseModel):
    business_name: str = Field(min_length=1, max_length=255)
    timezone_name: str = Field(default="America/Toronto", min_length=1, max_length=80)
    opening_hours: dict[str, Any] = Field(default_factory=dict)
    services: list[VoiceServiceConfig] = Field(default_factory=list, max_length=100)
    transfer_phone: str | None = Field(default=None, pattern=r"^\+[1-9]\d{7,14}$")
    telnyx_phone_number: str | None = Field(default=None, pattern=r"^\+[1-9]\d{7,14}$")
    preferred_language: str = Field(default="fr", min_length=2, max_length=16)
    retell_agent_id: str | None = Field(default=None, min_length=1, max_length=128)
    retell_sip_uri: str | None = Field(default=None, pattern=r"^sips?:[^\s]+$")
    voice_id: str = Field(default="alloy", min_length=1, max_length=64)
    voice_provider: str = Field(default="openai", min_length=1, max_length=32)
    speech_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    personality_tone: str = Field(default="professionnel", min_length=1, max_length=64)
    custom_pronunciation: str | None = Field(default=None, max_length=255)
    farewell_message: str | None = Field(default=None, max_length=1000)
    enabled: bool = False

    @model_validator(mode="after")
    def validate_audio_configuration(self):
        if bool(self.retell_agent_id) != bool(self.retell_sip_uri):
            raise ValueError("Conversation provider agent and target must be configured together")
        if self.enabled and not self.retell_agent_id:
            raise ValueError("Inbound calls cannot be enabled without a real conversation provider")
        return self

    @field_validator("preferred_language")
    @classmethod
    def validate_preferred_language(cls, value: str) -> str:
        normalized = value.strip().casefold().replace("_", "-")
        if normalized not in BY_LOCALE and normalized not in BY_BCP47:
            raise ValueError("Voice language must use an existing Avenqo locale")
        return resolve_locale(value)

    @field_validator("opening_hours")
    @classmethod
    def validate_opening_hours(cls, value: dict[str, Any]) -> dict[str, Any]:
        valid_days = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
        if not set(value).issubset(valid_days):
            raise ValueError("Opening-hours keys must be weekday names in English")
        for day, hours in value.items():
            if not isinstance(hours, dict) or not {"open", "close"}.issubset(hours):
                raise ValueError(f"Opening hours for {day} must contain open and close times")
            opened = datetime_time.fromisoformat(str(hours["open"]))
            closed = datetime_time.fromisoformat(str(hours["close"]))
            if opened >= closed:
                raise ValueError(f"Opening time must precede closing time for {day}")
        return value


class VoiceConfigResponse(BaseModel):
    id: UUID
    business_name: str
    timezone_name: str
    opening_hours: dict[str, Any]
    services: list[dict[str, Any]]
    transfer_phone: str | None
    telnyx_phone_number: str | None = None
    preferred_language: str
    greeting_message: str
    retell_agent_id: str | None
    retell_sip_uri: str | None
    voice_api_key_last4: str
    voice_id: str = "alloy"
    voice_provider: str = "openai"
    speech_speed: float = 1.0
    personality_tone: str = "professionnel"
    custom_pronunciation: str | None = None
    farewell_message: str | None = None
    enabled: bool

    model_config = ConfigDict(from_attributes=True)


class VoiceConfigCreatedResponse(VoiceConfigResponse):
    voice_api_key: str


class VoiceToolRequest(BaseModel):
    call_id: str = Field(min_length=1, max_length=255)
    action_id: str = Field(min_length=1, max_length=255)
    arguments: dict[str, Any] = Field(default_factory=dict)


class VoiceToolResponse(BaseModel):
    success: bool
    result: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class VoiceNumberProvisionRequest(BaseModel):
    country_code: str = Field(pattern=r"^[A-Za-z]{2}$")
    phone_number: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    region: str | None = Field(default=None, max_length=120)
    locality: str | None = Field(default=None, max_length=120)
    number_type: str | None = Field(default=None, max_length=32)
    confirmed: bool = False
    quote_token: str | None = Field(default=None, max_length=12000)


class VoiceNumberReleaseRequest(BaseModel):
    confirmed: bool = False


class VoiceNumberAssignRequest(BaseModel):
    confirmed: bool = False


class VoiceSetupRequest(BaseModel):
    number_id: UUID | None = None
    confirmed: bool = False
    model_config = ConfigDict(extra="forbid")


class VoiceOwnedNumberRequest(BaseModel):
    phone_number: str = Field(pattern=r"^\+[1-9]\d{7,14}$")
    confirmed: bool = False
    model_config = ConfigDict(extra="forbid")


class VoicePinRequest(BaseModel):
    pin: SecretStr | str
    confirm_pin: SecretStr | str | None = None
    pin_confirmation: SecretStr | str | None = None
    current_password: SecretStr | str | None = None
    phone_number: str | None = None
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_pin_payload(self) -> VoicePinRequest:
        from backend.app.voice.auth import validate_voice_pin
        pin_val = self.pin.get_secret_value() if isinstance(self.pin, SecretStr) else str(self.pin)
        validate_voice_pin(pin_val)
        confirmation = self.confirm_pin or self.pin_confirmation
        if confirmation is not None:
            confirm_val = confirmation.get_secret_value() if isinstance(confirmation, SecretStr) else str(confirmation)
            if pin_val != confirm_val:
                raise ValueError("PIN and confirmation PIN do not match")
        if self.current_password is not None:
            pw_val = self.current_password.get_secret_value() if isinstance(self.current_password, SecretStr) else str(self.current_password)
            if pw_val == pin_val:
                raise ValueError("PIN must not be identical to your account password")
        return self

    @property
    def pin_value(self) -> str:
        return self.pin.get_secret_value() if isinstance(self.pin, SecretStr) else str(self.pin)

    @property
    def current_password_value(self) -> str | None:
        if self.current_password is None:
            return None
        return self.current_password.get_secret_value() if isinstance(self.current_password, SecretStr) else str(self.current_password)

    @property
    def confirm_pin_value(self) -> str | None:
        val = self.confirm_pin or self.pin_confirmation
        if val is None:
            return None
        return val.get_secret_value() if isinstance(val, SecretStr) else str(val)


class VoicePinSetupRequest(VoicePinRequest):
    pass


class VoicePhoneAccessRequest(BaseModel):
    enabled: bool
    model_config = ConfigDict(extra="forbid")


class VoiceMemberAccessRequest(BaseModel):
    enabled: bool
    model_config = ConfigDict(extra="forbid")


class CheckAvailabilityArguments(BaseModel):
    date: date
    service_name: str = Field(min_length=1, max_length=200)


class BookAppointmentArguments(BaseModel):
    confirmed: bool = False
    caller_name: str = Field(min_length=1, max_length=255)
    caller_phone: str = Field(min_length=8, max_length=40)
    service_name: str = Field(min_length=1, max_length=200)
    starts_at: datetime


class RescheduleAppointmentArguments(BaseModel):
    confirmed: bool = False
    appointment_id: UUID
    starts_at: datetime


class CancelAppointmentArguments(BaseModel):
    confirmed: bool = False
    appointment_id: UUID
    reason: str | None = Field(default=None, max_length=500)


class TransferArguments(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class BusinessInfoArguments(BaseModel):
    pass


class TakeMessageArguments(BaseModel):
    caller_name: str = Field(min_length=1, max_length=255)
    caller_phone: str = Field(min_length=8, max_length=40)
    message: str = Field(min_length=1, max_length=4000)


class VoiceCatalogItem(BaseModel):
    id: str
    name: str
    provider: str
    gender: str
    style: str
    style_label: str
    description: str
    sample_url: str | None = None
    supported_languages: list[str]
    latency_tier: str
    quality_tier: str


class VoicePreviewRequest(BaseModel):
    voice_id: str = Field(default="alloy", min_length=1, max_length=64)
    text: str | None = Field(default=None, max_length=500)
    language: str | None = Field(default="fr", max_length=16)



class RetellWebhookEnvelope(BaseModel):
    event: str
    call: dict[str, Any]