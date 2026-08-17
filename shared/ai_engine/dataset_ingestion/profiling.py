"""Profilage automatique de colonnes sans jamais journaliser les valeurs brutes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from shared.ai_engine.dataset_ingestion.type_inference import SemanticType, infer_semantic_type

_MAX_SAMPLE_VALUES = 3


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    name: str
    semantic_type: SemanticType
    non_null_count: int
    null_ratio: float
    unique_count: int
    unique_ratio: float
    sample_values: tuple[str, ...] = ()
    min_value: float | None = None
    max_value: float | None = None
    mean_value: float | None = None
    median_value: float | None = None
    min_date: str | None = None
    max_date: str | None = None
    avg_text_length: float | None = None


@dataclass(frozen=True, slots=True)
class CompanyDatasetProfile:
    row_count: int
    column_count: int
    columns: tuple[ColumnProfile, ...] = field(default_factory=tuple)


class DatasetProfiler:
    """Construit un `CompanyDatasetProfile` générique, sans logique métier figée."""

    def profile(self, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> CompanyDatasetProfile:
        column_profiles = tuple(self._profile_column(name, rows) for name in columns)
        return CompanyDatasetProfile(
            row_count=len(rows),
            column_count=len(columns),
            columns=column_profiles,
        )

    def _profile_column(self, name: str, rows: Sequence[Mapping[str, Any]]) -> ColumnProfile:
        values = [row.get(name) for row in rows]
        present = [value for value in values if value is not None and str(value).strip() != ""]
        total = len(values)
        non_null = len(present)
        distinct_values = list({str(value): value for value in present}.values())
        semantic_type = infer_semantic_type(name, values)

        sample_values = tuple(str(value) for value in distinct_values[:_MAX_SAMPLE_VALUES])

        numeric_values = [
            float(value) for value in present
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        min_value = min(numeric_values) if numeric_values else None
        max_value = max(numeric_values) if numeric_values else None
        mean_value = round(sum(numeric_values) / len(numeric_values), 4) if numeric_values else None
        median_value = self._median(numeric_values) if numeric_values else None

        date_values = [value for value in present if isinstance(value, (datetime, date))]
        min_date = min(date_values).isoformat() if date_values else None
        max_date = max(date_values).isoformat() if date_values else None

        text_values = [str(value) for value in present if isinstance(value, str)]
        avg_text_length = (
            round(sum(len(value) for value in text_values) / len(text_values), 2)
            if semantic_type in (SemanticType.TEXT, SemanticType.CATEGORICAL) and text_values
            else None
        )

        return ColumnProfile(
            name=name,
            semantic_type=semantic_type,
            non_null_count=non_null,
            null_ratio=round((total - non_null) / total, 4) if total else 0.0,
            unique_count=len(distinct_values),
            unique_ratio=round(len(distinct_values) / non_null, 4) if non_null else 0.0,
            sample_values=sample_values,
            min_value=min_value,
            max_value=max_value,
            mean_value=mean_value,
            median_value=median_value,
            min_date=min_date,
            max_date=max_date,
            avg_text_length=avg_text_length,
        )

    @staticmethod
    def _median(values: list[float]) -> float:
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2 == 0:
            return round((ordered[mid - 1] + ordered[mid]) / 2, 4)
        return round(ordered[mid], 4)
