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
        null_cells_detected = 0
        invalid_row_flags: list[bool] = []

        cleaned_rows: list[dict[str, Any]] = []
        for row in deduplicated:
            cleaned_row = dict(row)
            row_invalid = False
            for original_column, canonical_field in mapping.items():
                if original_column not in cleaned_row:
                    continue
                value = cleaned_row[original_column]
                expected_types = CANONICAL_FIELD_SEMANTIC_TYPE.get(canonical_field, ())

                if SemanticType.DATETIME in expected_types:
                    converted, ok = self._convert_date(value)
                    if value is not None and ok:
                        date_conversions += 1
                    if value is not None and not ok:
                        row_invalid = True
                    cleaned_row[original_column] = converted
                elif any(t in expected_types for t in (SemanticType.CURRENCY, SemanticType.FLOAT, SemanticType.INTEGER)):
                    converted, ok = self._convert_numeric(value)
                    if value is not None and ok:
                        numeric_conversions += 1
                    if value is not None and not ok:
                        row_invalid = True
                    cleaned_row[original_column] = converted
                elif SemanticType.BOOLEAN in expected_types:
                    cleaned_row[original_column] = self._convert_boolean(value)

            for value in cleaned_row.values():
                if value is None:
                    null_cells_detected += 1
                if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
                    row_invalid = True

            invalid_row_flags.append(row_invalid)
            cleaned_rows.append(cleaned_row)

        return tuple(cleaned_rows), CleaningReport(
            rows_before=rows_before,
            rows_after=len(cleaned_rows),
            duplicates_removed=duplicates_removed,
            numeric_conversions=numeric_conversions,
            date_conversions=date_conversions,
            null_cells_detected=null_cells_detected,
            invalid_rows=sum(invalid_row_flags),
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
    def _convert_boolean(value: Any) -> Any:
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in _BOOLEAN_TRUE:
                return True
            if lowered in _BOOLEAN_FALSE:
                return False
        return value
