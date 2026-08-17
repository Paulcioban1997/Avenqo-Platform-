"""Recherche d'hyperparamètres Forecasting (à brancher : Optuna avec validation croisée temporelle)."""

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer


class ForecastingHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Aucune recherche pour l'instant ; branchera Optuna plus tard."""
