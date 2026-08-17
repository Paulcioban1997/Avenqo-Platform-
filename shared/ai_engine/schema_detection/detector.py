"""Détection automatique du schéma et de la qualité des données."""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class FieldProfile:
    name: str
    inferred_type: str
    nullable: bool
    missing_count: int
    distinct_count: int


@dataclass(frozen=True, slots=True)
class SchemaReport:
    fields: tuple[FieldProfile, ...]
    row_count: int
    duplicate_count: int


class SchemaDetector:
    """Analyse des lignes génériques sans supposer de colonnes métier."""

    def detect(self, rows: Iterable[Mapping[str, Any]]) -> SchemaReport:
        materialized = [dict(row) for row in rows]
        field_names = tuple(dict.fromkeys(key for row in materialized for key in row))
        profiles = tuple(self._profile(name, materialized) for name in field_names)
        fingerprints = [repr(sorted(row.items())) for row in materialized]
        duplicate_count = sum(count - 1 for count in Counter(fingerprints).values())
        return SchemaReport(profiles, len(materialized), duplicate_count)

    def _profile(self, name: str, rows: list[dict[str, Any]]) -> FieldProfile:
        values = [row.get(name) for row in rows]
        present = [value for value in values if value is not None]
        inferred = self._type_name(present[0]) if present else "unknown"
        return FieldProfile(
            name=name,
            inferred_type=inferred,
            nullable=len(present) != len(values),
            missing_count=len(values) - len(present),
            distinct_count=len({repr(value) for value in present}),
        )

    @staticmethod
    def _type_name(value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, (datetime, date)):
            return "datetime"
        if isinstance(value, str):
            return "string"
        return type(value).__name__
