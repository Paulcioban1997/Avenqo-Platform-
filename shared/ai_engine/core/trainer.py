"""Étape d'entraînement commune, réutilisée à l'identique par chaque famille IA."""

from typing import Any

from shared.ai_engine.contracts import DatasetArtifact, TrainingCandidate


class Trainer:
    """Délègue l'entraînement au candidat lui-même, de façon identique pour chaque famille."""

    def train(self, candidate: TrainingCandidate, dataset: DatasetArtifact) -> Any:
        return candidate.train(dataset)
