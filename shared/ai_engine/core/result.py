"""Résultat commun retourné par la stratégie d'exécution de n'importe quelle famille."""

from dataclasses import dataclass
from typing import Any

from shared.ai_engine.contracts import EvaluationResult


@dataclass(frozen=True, slots=True)
class AutoMLResult:
    """Candidat sélectionné, son modèle entraîné et son évaluation."""

    candidate_id: str
    model: Any
    evaluation: EvaluationResult
