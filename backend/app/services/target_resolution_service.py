"""Résout automatiquement la colonne cible d'un dataset pour une tâche donnée.

L'utilisateur ne choisit jamais manuellement de colonne cible : ce service
réutilise les correspondances déjà prévues par l'AI Engine
(`shared.ai_engine.mapping`) pour trouver, parmi les colonnes réellement
présentes dans le CSV importé, celle qui correspond à la cible métier
attendue par la tâche (via alias exacts d'abord, puis similarité sémantique).
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Sequence

from shared.ai_engine.mapping.semantic_mapper import SemanticMapper
from shared.ai_engine.mapping.synonym_mapper import SynonymMapper

_CANONICAL_TARGET = "target"


class TargetColumnUnresolved(ValueError):
    """Aucune colonne du dataset ne correspond à la cible attendue par la tâche."""


class TargetResolutionService:
    """Trouve automatiquement quelle colonne source correspond à la cible métier."""

    def __init__(self, semantic_threshold: float = 0.72) -> None:
        self._semantic_threshold = semantic_threshold

    def resolve(self, columns: Sequence[str], target_aliases: Sequence[str]) -> str:
        synonym_mapper = SynonymMapper({_CANONICAL_TARGET: set(target_aliases)})
        exact_match = synonym_mapper.map_columns(columns, [_CANONICAL_TARGET])
        if exact_match:
            return next(iter(exact_match))

        semantic_mapper = SemanticMapper(self._similarity)
        semantic_match = semantic_mapper.map_columns(
            columns, target_aliases, threshold=self._semantic_threshold
        )
        if semantic_match:
            return next(iter(semantic_match))

        raise TargetColumnUnresolved(
            "No column in this dataset could be automatically matched to the "
            "expected business target for this task."
        )

    @staticmethod
    def _similarity(source: str, target: str) -> float:
        return SequenceMatcher(None, source.lower(), target.lower()).ratio()
