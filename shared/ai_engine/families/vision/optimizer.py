"""Recherche d'hyperparamètres Vision (à brancher : KerasTuner / Optuna)."""

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer


class VisionHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Aucune recherche pour l'instant ; branchera KerasTuner/Optuna plus tard."""
