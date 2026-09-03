from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CentralAIRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=12000)
    page_context: str | None = Field(default=None, max_length=200)
    locale: str | None = Field(default=None, min_length=2, max_length=16, pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z]{2})?$")


class CentralAIResponse(BaseModel):
    selected_agent: str | None
    status: str
    answer: str | None
    remaining_ai_credits: int | None
    agent_availability: str
    conversation_id: UUID