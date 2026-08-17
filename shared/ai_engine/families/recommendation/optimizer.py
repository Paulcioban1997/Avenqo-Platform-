"""Recherche d'hyperparamètres Recommendation (à brancher : Optuna / RandomizedSearchCV)."""

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer


class RecommendationHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Aucune recherche pour l'instant ; branchera Optuna/RandomizedSearchCV plus tard."""
