"""Recherche d'hyperparamètres Synthetic Data (à brancher : Optuna)."""

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer


class SyntheticDataHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Aucune recherche pour l'instant ; branchera Optuna plus tard."""
