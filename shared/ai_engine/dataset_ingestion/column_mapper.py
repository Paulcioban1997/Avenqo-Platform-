"""Mapping sémantique multi-signal des colonnes vers le vocabulaire canonique.

Combine délibérément PLUSIEURS signaux (alias exact, normalisation, tokens,
similarité de nom, type sémantique du contenu réel) au lieu de se fier à la
seule similarité de nom : une colonne `customer_review` (texte) ne doit
jamais être confondue avec `customer_id` (identifiant), même si les deux
partagent le préfixe "customer".
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from enum import Enum
from typing import Any

from shared.ai_engine.dataset_ingestion.canonical_fields import (
    CANONICAL_FIELD_ALIASES,
    CANONICAL_FIELD_SEMANTIC_TYPE,
    CANONICAL_FIELDS,
)
from shared.ai_engine.dataset_ingestion.type_inference import SemanticType, infer_semantic_type

_NORMALIZE = re.compile(r"[^a-z0-9]")


class MappingConfidence(str, Enum):
    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNRESOLVED = "unresolved"


class MappingProvenance(str, Enum):
    AUTO = "auto"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class ColumnMappingSuggestion:
    original_column: str
    suggested_field: str | None
    confidence: MappingConfidence
    score: float
    alternatives: tuple[str, ...]
    reason: str


class SemanticColumnMapper:
    """Propose un mapping colonne -> champ canonique à partir de signaux combinés."""

    def __init__(self, name_similarity_threshold: float = 0.6) -> None:
        self._threshold = name_similarity_threshold

    def suggest(
        self,
        columns: Sequence[str],
        rows: Sequence[Mapping[str, Any]],
    ) -> tuple[ColumnMappingSuggestion, ...]:
        suggestions = []
        for column in columns:
            values = [row.get(column) for row in rows]
            column_type = infer_semantic_type(column, values)
            suggestions.append(self._suggest_for_column(column, column_type))
        return tuple(suggestions)

    def _suggest_for_column(self, column: str, column_type: SemanticType) -> ColumnMappingSuggestion:
        normalized_column = self._normalize(column)

        exact_field = self._exact_alias_match(normalized_column)
        if exact_field is not None:
            return ColumnMappingSuggestion(
                original_column=column,
                suggested_field=exact_field,
                confidence=MappingConfidence.EXACT,
                score=1.0,
                alternatives=(),
                reason=(
                    f"Alias exact reconnu pour '{exact_field}' "
                    f"(type détecté compatible : {column_type.value})."
                ),
            )

        scored: list[tuple[str, float, bool]] = []
        for field in CANONICAL_FIELDS:
            name_score = self._best_name_similarity(normalized_column, field)
            type_compatible = column_type in CANONICAL_FIELD_SEMANTIC_TYPE.get(field, ())
            scored.append((field, name_score, type_compatible))

        scored.sort(key=lambda item: item[1], reverse=True)
        if not scored or scored[0][1] < self._threshold:
            return ColumnMappingSuggestion(
                original_column=column,
                suggested_field=None,
                confidence=MappingConfidence.UNRESOLVED,
                score=scored[0][1] if scored else 0.0,
                alternatives=tuple(field for field, _, _ in scored[:3]),
                reason="Aucune correspondance suffisante avec le vocabulaire métier.",
            )

        best_field, best_score, best_type_ok = scored[0]
        alternatives = tuple(field for field, _, _ in scored[1:4])

        if not best_type_ok:
            # Signal de nom fort mais type incompatible : jamais un mapping à
            # haute confiance (évite le faux positif customer_id/customer_review).
            return ColumnMappingSuggestion(
                original_column=column,
                suggested_field=best_field,
                confidence=MappingConfidence.LOW,
                score=best_score,
                alternatives=alternatives,
                reason=(
                    f"Nom proche de '{best_field}' mais type détecté "
                    f"'{column_type.value}' incompatible : nécessite une revue manuelle."
                ),
            )

        if best_score >= 0.9:
            confidence = MappingConfidence.HIGH
        elif best_score >= 0.75:
            confidence = MappingConfidence.MEDIUM
        else:
            confidence = MappingConfidence.LOW

        return ColumnMappingSuggestion(
            original_column=column,
            suggested_field=best_field,
            confidence=confidence,
            score=best_score,
            alternatives=alternatives,
            reason=(
                f"Similarité de nom ({best_score:.2f}) et type "
                f"'{column_type.value}' compatible avec '{best_field}'."
            ),
        )

    def _exact_alias_match(self, normalized_column: str) -> str | None:
        for field, aliases in CANONICAL_FIELD_ALIASES.items():
            normalized_aliases = {self._normalize(alias) for alias in aliases} | {self._normalize(field)}
            if normalized_column in normalized_aliases:
                return field
        return None

    def _best_name_similarity(self, normalized_column: str, field: str) -> float:
        candidates = {self._normalize(alias) for alias in CANONICAL_FIELD_ALIASES.get(field, ())}
        candidates.add(self._normalize(field))
        return max(SequenceMatcher(None, normalized_column, candidate).ratio() for candidate in candidates)

    @staticmethod
    def _normalize(value: str) -> str:
        return _NORMALIZE.sub("", value.lower())
