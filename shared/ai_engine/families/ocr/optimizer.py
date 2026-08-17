"""Recherche d'hyperparamètres OCR (à brancher : Optuna)."""

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer


class OCRHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Aucune recherche pour l'instant ; branchera Optuna plus tard."""
