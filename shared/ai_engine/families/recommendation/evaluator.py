"""Évaluation des candidats Recommendation : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class RecommendationEvaluator(Evaluator):
    """Point d'extension pour des métriques Recommendation dédiées (ex : NDCG, recall@k)."""
