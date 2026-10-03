"""Tenant-owned voice-agent configuration and call records."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class VoiceBusinessConfig(TimestampMixin, Base):
    __tablename__ = "voice_business_configs"
    __table_args__ = (UniqueConstraint("company_id", name="uq_voice_business_config_company"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    timezone_name: Mapped[str] = mapped_column(String(80), nullable=False, default="America/Toronto")
    opening_hours: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    services: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    transfer_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    telnyx_phone_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(8), nullable=False, default="fr")
    greeting_message: Mapped[str] = mapped_column(Text, nullable=False)
    retell_agent_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    retell_sip_uri: Mapped[str] = mapped_column(String(512), nullable=False)
    voice_api_key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    voice_api_key_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=False)


class VoiceCall(TimestampMixin, Base):
    __tablename__ = "voice_calls"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    config_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("voice_business_configs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    telnyx_call_control_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    retell_call_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    caller_phone: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="incoming", index=True)
    uncertainty_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    appointment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_appointments.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    sms_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceToolAction(Base):
    __tablename__ = "voice_tool_actions"
    __table_args__ = (
        UniqueConstraint("config_id", "action_id", name="uq_voice_tool_action_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    config_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("voice_business_configs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    action_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class VoiceCentralSession(TimestampMixin, Base):
    """Browser/mobile Voice Central session; raw audio is never stored."""

    __tablename__ = "voice_central_sessions"
    __table_args__ = (UniqueConstraint("company_id", "request_id", name="uq_voice_central_session_request"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    company_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    conversation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    stt_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tts_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    realtime_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    stt_input_seconds: Mapped[float] = mapped_column(nullable=False, default=0)
    tts_output_seconds: Mapped[float] = mapped_column(nullable=False, default=0)
    last_audio_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=-1, server_default="-1")
    detected_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    detected_locale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    language_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_locale: Mapped[str | None] = mapped_column(String(16), nullable=True)
    interruption_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
