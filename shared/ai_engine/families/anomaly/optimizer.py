"""Recherche d'hyperparamètres Anomaly Detection (à brancher : RandomizedSearchCV / Optuna)."""

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer


class AnomalyDetectionHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Aucune recherche pour l'instant ; branchera RandomizedSearchCV/Optuna plus tard."""
