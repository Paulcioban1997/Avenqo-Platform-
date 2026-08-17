from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


class DatasetValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"


class DatasetVersionState(StrEnum):
    UPLOADED = "uploaded"
    VALIDATED = "validated"
    READY = "ready"
    ARCHIVED = "archived"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class DatasetValidationIssue:
    code: str
    field: str | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class DatasetValidationResult:
    status: DatasetValidationStatus
    issues: tuple[DatasetValidationIssue, ...] = ()
    row_count: int = 0
    column_count: int = 0
    missing_values: int = 0
    duplicate_rows: int = 0
    quality_score: float = 1.0


@dataclass(frozen=True, slots=True)
class DatasetVersionRecord:
    dataset_id: str
    version_number: int
    version_label: str
    module_code: str
    source_uri: str
    filename: str
    checksum: str
    status: DatasetVersionState = DatasetVersionState.READY
    is_current: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)
