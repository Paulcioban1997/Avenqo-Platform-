from uuid import UUID

from pydantic import BaseModel, Field


class RetailAssistantRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    source_id: UUID | None = None
    source_type: str | None = None


class RetailAssistantResponse(BaseModel):
    answer: str
    suggested_actions: list[str]
    grounded_source: str | None = None
    source_id: str | None = None