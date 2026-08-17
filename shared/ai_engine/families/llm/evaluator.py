"""Évaluation des candidats LLM : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class LLMEvaluator(Evaluator):
    """Point d'extension pour des métriques LLM dédiées (ex : perplexité, taux de victoire)."""
