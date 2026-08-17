"""Recherche d'hyperparamètres RAG (à brancher : Optuna sur les paramètres du retriever/reranker)."""

from shared.ai_engine.core.optimizer import NoOpHyperparameterOptimizer


class RAGHyperparameterOptimizer(NoOpHyperparameterOptimizer):
    """Aucune recherche pour l'instant ; branchera Optuna plus tard."""
