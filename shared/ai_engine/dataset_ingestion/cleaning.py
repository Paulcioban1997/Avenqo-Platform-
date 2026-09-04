"""Nettoyage générique et non destructif d'un dataset d'entreprise (Phase 26).

Règles absolues : ne jamais supprimer massivement des lignes sans trace, ne
jamais inventer/imputer une valeur métier, ne jamais transformer tous les
outliers automatiquement. Seules les duplications EXACTES de lignes sont
supprimées, et chaque conversion est comptabilisée dans le `CleaningReport`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shared.ai_engine.dataset_ingestion.canonical_fields import CANONICAL_FIELD_SEMANTIC_TYPE
from shared.ai_engine.dataset_ingestion.type_inference import SemanticType

_CURRENCY_SYMBOLS = re.compile(r"[$€£,\s]")
_BOOLEAN_TRUE = {"true", "yes", "y", "1"}
_BOOLEAN_FALSE = {"false", "no", "n", "0"}


@dataclass(frozen=True, slots=True)
class CleaningReport:
    rows_before: int
    rows_after: int
    duplicates_removed: int
    numeric_conversions: int
    date_conversions: int
    null_cells_detected: int
    invalid_rows: int
    boolean_conversions: int = 0
    invalid_values_detected: int = 0
    invalid_values_corrected: int = 0
    column_reports: tuple["ColumnCleaningReport", ...] = ()


@dataclass(frozen=True, slots=True)
class ColumnCleaningReport:
    column_name: str
    canonical_field: str | None
    semantic_type: str
    missing_values_detected: int
    missing_values_corrected: int
    invalid_values_detected: int
    invalid_values_corrected: int
    numeric_conversions: int
    date_conversions: int
    boolean_conversions: int


class CompanyDatasetCleaner:
    """Nettoie un dataset déjà mappé vers le vocabulaire canonique."""

    def clean(
        self,
        rows: Sequence[Mapping[str, Any]],
        mapping: Mapping[str, str],
    ) -> tuple[tuple[dict[str, Any], ...], CleaningReport]:
        rows_before = len(rows)
        trimmed = [self._trim_row(row) for row in rows]

        deduplicated, duplicates_removed = self._drop_exact_duplicates(trimmed)

        numeric_conversions = 0
        date_conversions = 0
        boolean_conversions = 0
        null_cells_detected = 0
        invalid_values_detected = 0
        invalid_values_corrected = 0
        invalid_row_flags: list[bool] = []
        column_stats: dict[str, dict[str, Any]] = {}

        cleaned_rows: list[dict[str, Any]] = []
        for row in deduplicated:
            cleaned_row = dict(row)
            row_invalid = False
            for column_name in list(cleaned_row):
                canonical_field = mapping.get(column_name)
                expected_types = CANONICAL_FIELD_SEMANTIC_TYPE.get(canonical_field, ())
                stats = column_stats.setdefault(
                    column_name,
                    self._new_column_stats(column_name, canonical_field, expected_types),
                )
                value = cleaned_row[column_name]
                if value is None:
                    stats["missing_values_detected"] += 1
                    null_cells_detected += 1
                    continue

                original_value = value
                expected_types = CANONICAL_FIELD_SEMANTIC_TYPE.get(canonical_field, ())

                if SemanticType.DATETIME in expected_types:
                    converted, ok = self._convert_date(value)
                    if ok and converted != value:
                        date_conversions += 1
                        stats["date_conversions"] += 1
                    if not ok:
                        row_invalid = True
                        invalid_values_detected += 1
                        invalid_values_corrected += 1
                        stats["invalid_values_detected"] += 1
                        stats["invalid_values_corrected"] += 1
                        converted = None
                    cleaned_row[column_name] = converted
                elif any(t in expected_types for t in (SemanticType.CURRENCY, SemanticType.FLOAT, SemanticType.INTEGER)):
                    converted, ok = self._convert_numeric(value)
                    if ok and converted != value:
                        numeric_conversions += 1
                        stats["numeric_conversions"] += 1
                    if not ok:
                        row_invalid = True
                        invalid_values_detected += 1
                        invalid_values_corrected += 1
                        stats["invalid_values_detected"] += 1
                        stats["invalid_values_corrected"] += 1
                        converted = None
                    cleaned_row[column_name] = converted
                elif SemanticType.BOOLEAN in expected_types:
                    converted, changed = self._convert_boolean(value)
                    if changed:
                        boolean_conversions += 1
                        stats["boolean_conversions"] += 1
                    cleaned_row[column_name] = converted

                if original_value is not None and cleaned_row[column_name] is None:
                    null_cells_detected += 1

            for column_name, value in list(cleaned_row.items()):
                if value is None:
                    continue
                if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
                    row_invalid = True
                    invalid_values_detected += 1
                    invalid_values_corrected += 1
                    stats = column_stats.setdefault(
                        column_name,
                        self._new_column_stats(
                            column_name,
                            mapping.get(column_name),
                            CANONICAL_FIELD_SEMANTIC_TYPE.get(mapping.get(column_name), ()),
                        ),
                    )
                    stats["invalid_values_detected"] += 1
                    stats["invalid_values_corrected"] += 1
                    cleaned_row[column_name] = None

            invalid_row_flags.append(row_invalid)
            cleaned_rows.append(cleaned_row)

        column_reports = tuple(
            ColumnCleaningReport(**column_stats[name]) for name in sorted(column_stats)
        )

        return tuple(cleaned_rows), CleaningReport(
            rows_before=rows_before,
            rows_after=len(cleaned_rows),
            duplicates_removed=duplicates_removed,
            numeric_conversions=numeric_conversions,
            date_conversions=date_conversions,
            null_cells_detected=null_cells_detected,
            invalid_rows=sum(invalid_row_flags),
            boolean_conversions=boolean_conversions,
            invalid_values_detected=invalid_values_detected,
            invalid_values_corrected=invalid_values_corrected,
            column_reports=column_reports,
        )

    @staticmethod
    def _trim_row(row: Mapping[str, Any]) -> dict[str, Any]:
        cleaned: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, str):
                stripped = value.strip()
                cleaned[key] = stripped if stripped else None
            else:
                cleaned[key] = value
        return cleaned

    @staticmethod
    def _drop_exact_duplicates(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
        seen: set[str] = set()
        unique_rows: list[dict[str, Any]] = []
        duplicates = 0
        for row in rows:
            fingerprint = repr(sorted(row.items()))
            if fingerprint in seen:
                duplicates += 1
                continue
            seen.add(fingerprint)
            unique_rows.append(row)
        return unique_rows, duplicates

    @staticmethod
    def _convert_numeric(value: Any) -> tuple[Any, bool]:
        if value is None:
            return None, True
        if isinstance(value, bool):
            return value, False
        if isinstance(value, (int, float)):
            return value, True
        if isinstance(value, str):
            cleaned = _CURRENCY_SYMBOLS.sub("", value).rstrip("%")
            try:
                number = float(cleaned)
                return (int(number) if number.is_integer() else number), True
            except ValueError:
                return value, False
        return value, False

    @staticmethod
    def _convert_date(value: Any) -> tuple[Any, bool]:
        if value is None:
            return None, True
        if isinstance(value, datetime):
            return value.isoformat(), True
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed.isoformat(), True
            except ValueError:
                return value, False
        return value, False

    @staticmethod
    def _convert_boolean(value: Any) -> tuple[Any, bool]:
        if value is None or isinstance(value, bool):
            return value, False
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _BOOLEAN_TRUE:
                return True, True
            if lowered in _BOOLEAN_FALSE:
                return False, True
        return value, False

    @staticmethod
    def _new_column_stats(
        column_name: str,
        canonical_field: str | None,
        expected_types: Sequence[SemanticType],
    ) -> dict[str, Any]:
        semantic_type = "text"
        if SemanticType.DATETIME in expected_types:
            semantic_type = "datetime"
        elif any(
            t in expected_types
            for t in (SemanticType.CURRENCY, SemanticType.FLOAT, SemanticType.INTEGER)
        ):
            semantic_type = "numeric"
        elif SemanticType.BOOLEAN in expected_types:
            semantic_type = "boolean"
        elif not expected_types:
            semantic_type = "unmapped"
        return {
            "column_name": column_name,
            "canonical_field": canonical_field,
            "semantic_type": semantic_type,
            "missing_values_detected": 0,
            "missing_values_corrected": 0,
            "invalid_values_detected": 0,
            "invalid_values_corrected": 0,
            "numeric_conversions": 0,
            "date_conversions": 0,
            "boolean_conversions": 0,
        }
