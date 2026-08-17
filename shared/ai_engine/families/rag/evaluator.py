"""Évaluation des candidats RAG : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class RAGEvaluator(Evaluator):
    """Point d'extension pour des métriques RAG dédiées (ex : recall de récupération, fidélité de la réponse)."""
