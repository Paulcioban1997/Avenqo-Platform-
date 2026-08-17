"""Recherche d'hyperparamètres Deep Learning (à brancher : KerasTuner)."""

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer


class DeepLearningHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Aucune recherche pour l'instant ; branchera KerasTuner plus tard."""
