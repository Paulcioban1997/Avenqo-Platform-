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
    std_value: float | None = None
    p25_value: float | None = None
    p75_value: float | None = None
    outlier_count: int | None = None
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
        std_value = self._std(numeric_values, mean_value) if len(numeric_values) > 1 else None
        p25_value = self._quantile(numeric_values, 0.25) if numeric_values else None
        p75_value = self._quantile(numeric_values, 0.75) if numeric_values else None
        outlier_count = (
            self._iqr_outlier_count(numeric_values, p25_value, p75_value)
            if numeric_values and p25_value is not None and p75_value is not None
            else None
        )

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
            std_value=std_value,
            p25_value=p25_value,
            p75_value=p75_value,
            outlier_count=outlier_count,
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

    @staticmethod
    def _std(values: list[float], mean_value: float | None) -> float:
        mean = mean_value if mean_value is not None else sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        return round(variance ** 0.5, 4)

    @staticmethod
    def _quantile(values: list[float], fraction: float) -> float:
        ordered = sorted(values)
        if len(ordered) == 1:
            return round(ordered[0], 4)
        position = fraction * (len(ordered) - 1)
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        weight = position - lower
        return round(ordered[lower] + (ordered[upper] - ordered[lower]) * weight, 4)

    @staticmethod
    def _iqr_outlier_count(values: list[float], p25: float | None, p75: float | None) -> int:
        if p25 is None or p75 is None:
            return 0
        iqr = p75 - p25
        if iqr <= 0:
            return 0
        lower_bound = p25 - 1.5 * iqr
        upper_bound = p75 + 1.5 * iqr
        return sum(1 for value in values if value < lower_bound or value > upper_bound)
