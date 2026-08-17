"""Contrat public de l'assistant métier RetailSense."""

from pydantic import BaseModel, Field


class RetailAssistantRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class RetailAssistantResponse(BaseModel):
    answer: str
    suggested_actions: list[str]