"""Schémas HTTP du pipeline universel d'ingestion (Phase 26)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from backend.app.models import DatasetStatus


class CompanyDatasetUploadResponse(BaseModel):
    dataset_id: UUID
    version: int
    status: DatasetStatus
    rows: int
    columns: int


class ColumnMappingSuggestionResponse(BaseModel):
    original_column: str
    suggested_field: str | None
    confidence: str
    score: float
    alternatives: tuple[str, ...]
    reason: str


class ColumnProfileResponse(BaseModel):
    name: str
    semantic_type: str
    non_null_count: int
    null_ratio: float
    unique_count: int
    unique_ratio: float
    sample_values: tuple[str, ...]
    min_value: float | None
    max_value: float | None
    mean_value: float | None
    median_value: float | None
    min_date: str | None
    max_date: str | None
    avg_text_length: float | None


class CapabilityReadinessResponse(BaseModel):
    capability: str
    ready: bool
    missing_fields: tuple[str, ...]
    warnings: tuple[str, ...]


class CompanyDatasetProfileResponse(BaseModel):
    dataset_id: UUID
    status: DatasetStatus
    uploaded_at: datetime
    row_count: int
    column_count: int
    columns: tuple[ColumnProfileResponse, ...]
    mapping_suggestions: tuple[ColumnMappingSuggestionResponse, ...]
    review_required: bool
    quality_status: str | None
    quality_reasons: tuple[str, ...]
    capability_readiness: tuple[CapabilityReadinessResponse, ...]


class DatasetCleaningDetailResponse(BaseModel):
    dataset_id: UUID
    name: str
    status: str
    cleaning_status: str
    quality_reasons: list[str]
    version: int
    timestamp: datetime
    summary: dict[str, Any]
    original_preview: list[dict[str, Any]]
    cleaned_preview: list[dict[str, Any]]
    preview_offset: int
    preview_limit: int
    preview_total: int
    transformation_history: list[dict[str, Any]]


class MappingOverrideRequest(BaseModel):
    mapping: dict[str, str]


class MappingOverrideResponse(BaseModel):
    dataset_id: UUID
    status: DatasetStatus
    mapping: dict[str, str]
    approved: bool


class CapabilityDatasetResponse(BaseModel):
    """Réponse Phase 27 : confirmation que `capability` est prête à consommer

    ce dataset, sans jamais exposer les lignes brutes ni un objet technique
    (pandas/sklearn) au client.
    """

    dataset_id: UUID
    dataset_version: int
    capability: str
    required_fields: tuple[str, ...]
    available_fields: tuple[str, ...]
    row_count: int
    warnings: tuple[str, ...]
    adapter_version: str
