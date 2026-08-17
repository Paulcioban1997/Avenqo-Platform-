"""Schémas HTTP des datasets tenant-isolés."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

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
    uploaded_at: datetime
    columns: list[FieldProfileResponse]
    distributions: dict[str, dict[str, int]]