from __future__ import annotations

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class MemoryCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    scope: str = Field(default="user", pattern="^(user|company)$")
    memory_type: str = Field(default="semantic")
    source_module: str = Field(default="central")
    conversation_id: UUID | None = None
    metadata: dict[str, object] | None = None


class MemoryUpdateRequest(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    scope: str | None = Field(default=None, pattern="^(user|company)$")
    memory_type: str | None = None


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=50)
    scope: str | None = Field(default=None, pattern="^(user|company)$")
    include_company_shared: bool = Field(default=True)


class MemoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    user_id: UUID
    conversation_id: UUID | None
    memory_scope: str
    memory_type: str
    source_module: str
    content: str
    metadata_json: dict[str, object] | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class MemoryListResponse(BaseModel):
    memories: list[MemoryResponse]
    total: int


class MemoryConfigResponse(BaseModel):
    enabled: bool
    backend: str
    max_context_items: int
