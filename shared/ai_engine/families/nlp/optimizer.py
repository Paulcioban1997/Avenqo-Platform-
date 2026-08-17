"""Recherche d'hyperparamètres NLP (à brancher : Optuna / HuggingFace hyperparameter_search)."""

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer


class NLPHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Aucune recherche pour l'instant ; branchera Optuna plus tard."""
