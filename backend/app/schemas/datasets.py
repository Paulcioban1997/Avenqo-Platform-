"""Schémas HTTP des datasets tenant-isolés."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.models import DatasetStatus


class FieldProfileResponse(BaseModel):
    name: str
    inferred_type: str
    nullable: bool
    missing_count: int
    distinct_count: int


class DatasetResponse(BaseModel):
    id: UUID
    name: str
    type: str
    module_code: str
    rows_count: int
    columns_count: int
    numerical_columns: int
    categorical_columns: int
    missing_values: int
    duplicates: int
    quality_score: float
    status: DatasetStatus
    pipeline_status: str
    training_status: str | None = None
    training_retryable: bool = False
    uploaded_at: datetime
    columns: list[FieldProfileResponse]
    distributions: dict[str, dict[str, int]]


class DatasetDeleteSelectionRequest(BaseModel):
    dataset_ids: list[UUID] = Field(min_length=1, max_length=100)


class DatasetDeleteSelectionResponse(BaseModel):
    deleted_ids: list[UUID]
    deleted_count: int
