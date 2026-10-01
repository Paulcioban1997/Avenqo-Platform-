"""Schémas Avenqo Platform Support AI (Phase 32) — mirroir de `schemas/ai_chat.py`."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateSupportConversationRequest(StrictSchema):
    title: str = Field(min_length=1, max_length=200)


class SendSupportMessageRequest(StrictSchema):
    content: str = Field(min_length=1, max_length=4000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=100)


class SupportConversationResponse(StrictSchema):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class SupportMessageResponse(StrictSchema):
    id: UUID
    role: str
    content: str
    created_at: datetime


class SupportSourceResponse(StrictSchema):
    type: str
    identifier: str
    name: str
    metadata: dict[str, object]


class SupportChatMessageResponse(SupportMessageResponse):
    sources: list[SupportSourceResponse]


class SupportConversationDetailResponse(SupportConversationResponse):
    messages: list[SupportMessageResponse]
