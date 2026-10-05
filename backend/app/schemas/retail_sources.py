from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RetailSourceResponse(BaseModel):
    source_type: str
    source_id: UUID
    dataset_id: UUID | None
    connection_id: UUID | None
    display_name: str
    provider: str | None
    status: str
    last_synchronized_at: datetime | None
    active: bool
    enabled: bool = False


class RetailSourceSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_type: str
    source_id: UUID | None = None


class RetailSourceStateRequest(BaseModel):
    source_type: str
    source_id: UUID
    enabled: bool