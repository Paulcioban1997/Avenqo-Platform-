"""Évaluation des candidats NLP : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class NLPEvaluator(Evaluator):
    """Point d'extension pour des métriques NLP dédiées (ex : F1, perplexité)."""
