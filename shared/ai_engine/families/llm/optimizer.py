"""Recherche d'hyperparamètres LLM (à brancher : Optuna sur les paramètres de fine-tuning/LoRA)."""

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer


class LLMHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Aucune recherche pour l'instant ; branchera Optuna plus tard."""
