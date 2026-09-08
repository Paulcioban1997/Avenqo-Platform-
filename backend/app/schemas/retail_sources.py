from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


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


class RetailSourceSelectionRequest(BaseModel):
    source_type: str
    source_id: UUID