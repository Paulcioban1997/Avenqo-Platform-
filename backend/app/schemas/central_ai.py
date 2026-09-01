from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CentralAIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=12000)


class CentralAIResponse(BaseModel):
    selected_agent: str | None
    status: str
    answer: str | None
    remaining_ai_credits: int | None
    agent_availability: str
    conversation_id: UUID