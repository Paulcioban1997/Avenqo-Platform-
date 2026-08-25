from __future__ import annotations

from pydantic import BaseModel


class AssistantResponse(BaseModel):
    slug: str
    name_key: str
    description_key: str
    status: str
    category: str
    available: bool
