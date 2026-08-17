"""Base commune à tous les modèles pré-intégrés au catalogue mais pas encore entraînables.

Chaque famille pré-intègre ses modèles (ils existent, sont catalogués et peuvent être
sélectionnés) sans qu'ils soient pré-entraînés. La logique réelle d'entraînement de
chaque modèle sera ajoutée ultérieurement, fichier par fichier, sans jamais toucher
à l'architecture (strategy, trainer, optimizer, evaluator, candidates, registry).
"""

from typing import Any

from shared.ai_engine.contracts import DatasetArtifact


class UntrainedModel:
    """Modèle catalogué dont la logique d'entraînement sera implémentée plus tard."""

    candidate_id: str = "untrained-model"

    def train(self, dataset: DatasetArtifact) -> Any:
        raise NotImplementedError(
            f"{type(self).__name__} training will be implemented in a future iteration."
        )
