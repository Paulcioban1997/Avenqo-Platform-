"""Adapte un modèle du catalogue d'une famille en candidat entraînable (TrainingCandidate)."""

from dataclasses import dataclass
from typing import Any, Callable

from shared.ai_engine.contracts import DatasetArtifact


@dataclass(frozen=True, slots=True)
class ModelCandidate:
    """Enveloppe une fabrique de modèle du catalogue pour satisfaire TrainingCandidate."""

    candidate_id: str
    factory: Callable[[], Any]

    def train(self, dataset: DatasetArtifact) -> Any:
        return self.factory().train(dataset)
