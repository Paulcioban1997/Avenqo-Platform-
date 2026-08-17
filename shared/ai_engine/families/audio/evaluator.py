"""Évaluation des candidats Audio : délègue au service d'évaluation partagé."""

from shared.ai_engine.core.evaluator import Evaluator


class AudioEvaluator(Evaluator):
    """Point d'extension pour des métriques Audio dédiées (ex : word error rate)."""
