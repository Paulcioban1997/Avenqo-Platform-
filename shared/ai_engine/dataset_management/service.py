from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Iterable, Mapping

from shared.ai_engine.dataset_management.types import (
    DatasetValidationIssue,
    DatasetValidationResult,
    DatasetValidationStatus,
    DatasetVersionRecord,
    DatasetVersionState,
)


class DatasetManagementService:
    """Internal dataset management shared across the platform and backend services."""

    @staticmethod
    def validate_rows(rows: Iterable[Mapping[str, Any]]) -> DatasetValidationResult:
        materialized = [dict(row) for row in rows]
        if not materialized:
            return DatasetValidationResult(
                status=DatasetValidationStatus.INVALID,
                issues=(DatasetValidationIssue(code="empty_dataset", message="Dataset vide."),),
                row_count=0,
                column_count=0,
                quality_score=0.0,
            )

        column_names = tuple(dict.fromkeys(key for row in materialized for key in row))
        issues: list[DatasetValidationIssue] = []
        missing_values = 0
        duplicate_rows = 0

        if len(column_names) == 0:
            issues.append(DatasetValidationIssue(code="no_columns", message="Aucune colonne détectée."))

        for field_name in column_names:
            values = [row.get(field_name) for row in materialized]
            present = [value for value in values if value is not None and str(value).strip() != ""]
            missing_values += len(values) - len(present)

            if len(present) == 0:
                issues.append(
                    DatasetValidationIssue(
                        code="all_missing",
                        field=field_name,
                        message=f"La colonne '{field_name}' est vide.",
                    )
                )

            if len({repr(value) for value in present}) < len(present):
                duplicate_rows += 1

        duplicate_fingerprints = Counter(repr(sorted(row.items())) for row in materialized)
        duplicate_rows += sum(count - 1 for count in duplicate_fingerprints.values())

        total_cells = max(len(materialized) * len(column_names), 1)
        error_cells = missing_values + duplicate_rows
        quality_score = max(0.0, min(1.0, round(1 - (error_cells / total_cells), 4)))

        if issues:
            status = DatasetValidationStatus.WARNING
            if quality_score < 0.5:
                status = DatasetValidationStatus.INVALID
        else:
            status = DatasetValidationStatus.VALID

        return DatasetValidationResult(
            status=status,
            issues=tuple(issues),
            row_count=len(materialized),
            column_count=len(column_names),
            missing_values=missing_values,
            duplicate_rows=duplicate_rows,
            quality_score=quality_score,
        )

    @staticmethod
    def build_version_record(
        dataset_id: str,
        version_number: int,
        module_code: str,
        filename: str,
        source_uri: str,
        content: bytes,
        metadata: Mapping[str, Any] | None = None,
    ) -> DatasetVersionRecord:
        checksum = hashlib.sha256(content).hexdigest()
        version_label = f"v{version_number}"
        return DatasetVersionRecord(
            dataset_id=dataset_id,
            version_number=version_number,
            version_label=version_label,
            module_code=module_code,
            source_uri=source_uri,
            filename=filename,
            checksum=checksum,
            status=DatasetVersionState.READY,
            is_current=True,
            metadata=dict(metadata or {}),
        )
