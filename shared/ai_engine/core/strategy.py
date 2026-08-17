"""Contrat commun à toute stratégie d'exécution enregistrée dans l'AI Engine."""

from typing import Protocol, Sequence, runtime_checkable

from shared.ai_engine.contracts import DatasetArtifact, TrainingCandidate
from shared.ai_engine.core.execution_domain import ExecutionDomain
from shared.ai_engine.core.result import AutoMLResult


@runtime_checkable
class ExecutionStrategy(Protocol):
    """Entraîne, évalue et sélectionne le meilleur candidat d'une famille IA donnée."""

    domain: ExecutionDomain

    def execute(
        self,
        dataset: DatasetArtifact,
        candidates: Sequence[TrainingCandidate] | None = None,
    ) -> AutoMLResult: ...
