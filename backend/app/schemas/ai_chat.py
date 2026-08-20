from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateConversationRequest(StrictSchema):
    title: str = Field(min_length=1, max_length=200)


class SendMessageRequest(StrictSchema):
    content: str = Field(min_length=1, max_length=12000)


class ConversationResponse(StrictSchema):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageResponse(StrictSchema):
    id: UUID
    role: str
    content: str
    created_at: datetime


class SourceResponse(StrictSchema):
    type: str
    identifier: str
    name: str
    metadata: dict[str, object]


class ChatMessageResponse(MessageResponse):
    sources: list[SourceResponse]


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]