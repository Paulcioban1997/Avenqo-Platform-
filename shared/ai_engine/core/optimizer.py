"""Point d'extension pour la recherche d'hyperparamètres (étape 9 du pipeline AutoML).

Chaque famille pourra brancher GridSearchCV, RandomizedSearchCV, Optuna, KerasTuner ou
toute autre méthode adaptée en implémentant `HyperparameterOptimizer`, sans jamais
modifier la stratégie générique ni l'AI Engine.
"""

from typing import Protocol, runtime_checkable

from shared.ai_engine.contracts import DatasetArtifact, TrainingCandidate


@runtime_checkable
class HyperparameterOptimizer(Protocol):
    def optimize(
        self,
        candidate: TrainingCandidate,
        dataset: DatasetArtifact,
    ) -> TrainingCandidate: ...


class NoOpHyperparameterOptimizer:
    """Implémentation par défaut : aucune recherche tant qu'une méthode dédiée n'est pas branchée."""

    def optimize(
        self,
        candidate: TrainingCandidate,
        dataset: DatasetArtifact,
    ) -> TrainingCandidate:
        return candidate
