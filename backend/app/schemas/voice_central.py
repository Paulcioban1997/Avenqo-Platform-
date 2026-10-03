from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class VoiceSessionCreate(BaseModel):
    conversation_id: UUID
    locale: str | None = Field(default=None, min_length=2, max_length=16)
    request_id: str = Field(min_length=1, max_length=100)


class VoiceSessionResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    locale: str
    detected_language: str | None = None
    detected_locale: str | None = None
    language_confidence: float | None = None
    status: str
    stt_provider: str | None
    tts_provider: str | None
    realtime_provider: str | None
    text_fallback: bool
    voice_capability: str


class VoiceStreamTicketResponse(BaseModel):
    ticket: str
    realtime: bool


class VoiceTurnRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=12000)
    request_id: str = Field(min_length=1, max_length=100)


class VoiceTurnResponse(BaseModel):
    session_id: UUID
    conversation_id: UUID
    transcript: str
    answer: str | None
    status: str
    tts_status: str
    tts_provider: str | None
    remaining_ai_credits: int | None
