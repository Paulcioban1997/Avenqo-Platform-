"""Recherche d'hyperparamètres Audio (à brancher : KerasTuner / Optuna)."""

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer


class AudioHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Aucune recherche pour l'instant ; branchera KerasTuner/Optuna plus tard."""
